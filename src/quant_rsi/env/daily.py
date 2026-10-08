"""Deterministic synthetic daily paper execution; no real-market rule claims.

``simulate(task, pit_view, frozen)`` consumes only frozen synthetic inputs.
Money, prices, and rates are decimal strings in the input and output.
``sessions`` contain explicit open timestamps; ``orders`` contain decision,
signal and creation timestamps; ``bars`` are keyed by (session, entity).
Only ``certified_open_volume`` authorizes a definite fill. Costs are separate
cash deductions on the unadjusted opening reference notional, never price edits.
"""
from decimal import Decimal, InvalidOperation
from datetime import datetime

from quant_rsi.data.pit import instant


def _d(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError('finite decimal string or integer required')
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('invalid decimal') from exc
    if not result.is_finite():
        raise ValueError('finite decimal required')
    return result


def _nonnegative(value):
    result = _d(value)
    if result < 0:
        raise ValueError('nonnegative value required')
    return result


def _iso(value):
    return (value if isinstance(value, datetime) else instant(value)).isoformat()


def _integer(value, minimum):
    if type(value) is not int or value < minimum:
        raise ValueError('exact non-bool integer in allowed range required')
    return value


def _account(cash, positions, marks):
    if not cash.is_finite() or cash < 0:
        raise ValueError('nonnegative cash required; no financing contract')
    for lots in positions.values():
        for quantity, _ in lots:
            _integer(quantity, 0)
    value = sum((sum(q for q, _ in lots) * marks[e] for e, lots in positions.items()), Decimal(0))
    nav = cash + value
    if not value.is_finite() or value < 0 or not nav.is_finite() or nav < 0:
        raise ValueError('invalid marked account')
    return value, nav


def _rule(rules, at, board, venue, st, listing):
    matches = [r for r in rules if instant(r['from']) <= at
               and (r.get('to') is None or at < instant(r['to']))
               and r['board'] == board and r['venue'] == venue
               and r['st'] is st and r['listing'] is listing]
    if len(matches) != 1:
        raise ValueError('unknown or ambiguous historical market rule')
    rule = matches[0]
    _integer(rule['lot_size'], 1)
    _integer(rule['t_plus_sessions'], 0)
    if _nonnegative(rule['tick_size']) == 0:
        raise ValueError('invalid market rule')
    limit = _nonnegative(rule['price_limit_pct'])
    if limit >= 1:
        raise ValueError('invalid price limit')
    return rule


def _state(view, at, entity):
    listing = view.state(_iso(at), entity, 'listing')
    st = view.state(_iso(at), entity, 'ST')
    board = view.state(_iso(at), entity, 'board')
    venue = view.state(_iso(at), entity, 'venue')
    if type(listing) is not bool or type(st) is not bool or not isinstance(board, str) or not isinstance(venue, str):
        raise ValueError('invalid PIT market state')
    return board, venue, st, listing


def simulate(task, pit_view, frozen):
    """Return a JSON-serializable ledger or fail closed on missing/unknown inputs.

    Rule and execution-policy versions must match Task. ``bars`` are outcomes
    consumed at session open, never as decision-time observations. Corporate
    actions are PIT records of kind ``corporate_action`` effective at session
    open; a split ratio changes quantity and reference mark inversely, while a
    dividend moves value from the marked position to cash.
    """
    versions = {'env_version': task.env_version, 'market_rules_version': task.market_rules_version,
                'calendar_version': task.calendar_version, 'cost_model_version': task.cost_model_version,
                'execution_timing': task.execution_timing}
    if any(frozen.get(k) != v for k, v in versions.items()):
        raise ValueError('frozen execution version differs from Task')
    if frozen.get('synthetic') is not True or frozen.get('uncertain_policy') != 'BLOCK':
        raise ValueError('synthetic BLOCK policy required')
    if frozen.get('calendar_timezone') != 'UTC':
        raise ValueError('explicit synthetic UTC daily calendar required')
    if frozen.get('split_order_policy') != 'ADJUST_RESIDUAL_UNITS':
        raise ValueError('frozen split residual adjustment policy required')
    sessions = [instant(s) for s in frozen['sessions']]
    if not sessions or sessions != sorted(set(sessions)):
        raise ValueError('explicit ordered unique sessions required')
    trading_dates = tuple(s.date() for s in sessions)
    if len(set(trading_dates)) != len(trading_dates):
        raise ValueError('at most one daily session per frozen trading date')
    def sellable(acquired_date, current_date, delay):
        return sum(acquired_date < d <= current_date for d in trading_dates) >= delay
    rules, bars = frozen['rules'], frozen['bars']
    costs = frozen['costs']
    rates = {k: _nonnegative(costs[k]) for k in ('commission', 'tax', 'spread', 'slippage', 'impact')}
    stress = _nonnegative(frozen['capacity']['impact_stress'])
    cap = _nonnegative(frozen['capacity']['participation_cap'])
    capital = _nonnegative(frozen['capacity']['target_capital'])
    if cap > 1 or capital == 0:
        raise ValueError('invalid capacity')
    cash = _nonnegative(frozen['initial_cash'])
    if cash != capital:
        raise ValueError('initial cash must equal target capital')
    positions = {}
    marks = {}
    fills, decisions, navs, actions = [], [], [], []
    orders = frozen['orders']
    pending = []
    for order in orders:
        decision, signal, created = (instant(order[k]) for k in ('decision_at', 'signal_at', 'order_created_at'))
        if not decision <= signal <= created or order['side'] not in ('buy', 'sell'):
            raise ValueError('invalid order chronology or side')
        first = next((i for i, s in enumerate(sessions) if s > created), None)
        if first is None:
            raise ValueError('no later executable session')
        entity = order['entity']
        rule = _rule(rules, decision, *_state(pit_view, decision, entity))
        if rule['listing'] is not True:
            raise ValueError('order on unlisted security')
        qty = _integer(order['quantity'], 1)
        if qty % rule['lot_size']:
            raise ValueError('positive lot-aligned order required')
        adv_row = [r for r in pit_view.at(_iso(decision)) if r.entity == entity and r.kind == 'lagged_ADV']
        if len(adv_row) != 1 or instant(adv_row[0].data_spec.event_time) >= decision:
            raise ValueError('lagged ADV must be observed strictly before decision')
        adv = _nonnegative(adv_row[0].value)
        if adv == 0:
            raise ValueError('positive lagged ADV required')
        pending.append(dict(order=order, first=first, remaining=qty, adv=adv,
                            first_executable_at=_iso(sessions[first]), decision_rule=rule))
    for index, session in enumerate(sessions):
        stamp = _iso(session)
        trading_date = session.date()
        used_volume = {}
        used_notional = {}
        # Action records are visible at their actual effective time, regardless
        # of when an order was decided. Never apply the same action twice.
        for row in pit_view.at(stamp):
            if row.kind != 'corporate_action' or instant(row.data_spec.effective_from) != session:
                continue
            action = row.value
            entity = row.entity
            if action['type'] == 'split':
                ratio = _integer(action['ratio'], 1)
                rule = _rule(rules, session, *_state(pit_view, session, entity))
                for item in pending:
                    if (item['order']['entity'] == entity and item['remaining']
                            and instant(item['order']['order_created_at']) < session):
                        adjusted = item['remaining'] * ratio
                        if adjusted % rule['lot_size']:
                            raise ValueError('split residual not aligned to frozen lot')
                        item['remaining'] = adjusted
                if entity in positions:
                    positions[entity] = [(q * ratio, acquired) for q, acquired in positions[entity]]
                    marks[entity] /= ratio
            elif action['type'] == 'dividend':
                amount = _nonnegative(action['per_share'])
                if entity not in positions:
                    continue
                qty = sum(q for q, _ in positions[entity])
                if marks[entity] < amount:
                    raise ValueError('dividend exceeds mark')
                cash += amount * qty
                marks[entity] -= amount
            else:
                raise ValueError('unsupported corporate action')
            _account(cash, positions, marks)
            actions.append(dict(entity=entity, at=stamp, type=action['type']))
        for entity in positions:
            held_bar = bars.get(stamp, {}).get(entity)
            if held_bar is not None:
                marks[entity] = _nonnegative(held_bar['mark'])
                if marks[entity] == 0:
                    raise ValueError('invalid position mark')
                _account(cash, positions, marks)
        for item in pending:
            if index < item['first'] or item['remaining'] == 0:
                continue
            order = item['order']; entity = order['entity']; side = order['side']
            board, venue, st, listing = _state(pit_view, session, entity)
            rule = _rule(rules, session, board, venue, st, listing)
            status, reason, quantity = 'UNCERTAIN', 'daily bar does not certify fill', 0
            bar = bars.get(stamp, {}).get(entity)
            suspended = pit_view.state(stamp, entity, 'suspended')
            if type(suspended) is not bool:
                raise ValueError('unknown suspension state')
            if item['remaining'] % rule['lot_size']:
                raise ValueError('residual not aligned to frozen lot')
            if not listing or suspended:
                status, reason = 'NOT_EXECUTABLE', 'delisted or suspended'
            elif bar is None:
                status, reason = 'UNCERTAIN', 'missing execution bar'
            else:
                price = _nonnegative(bar['open']); previous = _nonnegative(bar['previous_close'])
                mark = _nonnegative(bar['mark'])
                tick = _d(rule['tick_size'])
                if price == 0 or previous == 0:
                    raise ValueError('invalid price or tick')
                if price % tick or mark == 0:
                    raise ValueError('price not on tick or mark invalid')
                marks[entity] = mark
                limit = _d(rule['price_limit_pct'])
                if (price > previous * (1 + limit) or price < previous * (1 - limit)):
                    status, reason = 'NOT_EXECUTABLE', 'price outside synthetic limit'
                elif (side == 'buy' and price == previous * (1 + limit)) or (side == 'sell' and price == previous * (1 - limit)):
                    status, reason = 'UNCERTAIN', 'limit queue cannot be inferred'
                elif 'certified_open_volume' in bar:
                    volume = _integer(bar['certified_open_volume'], 0)
                    lot = rule['lot_size']
                    maximum = max(0, min(item['remaining'], volume - used_volume.get(entity, 0),
                                     int((item['adv'] * cap - used_notional.get(entity, Decimal(0))) / price)))
                    if side == 'sell':
                        eligible = sum(q for q, acquired in positions.get(entity, [])
                                       if sellable(acquired, trading_date, rule['t_plus_sessions']))
                        maximum = min(maximum, eligible)
                    else:
                        maximum = min(maximum, int(cash / price))
                    quantity = maximum // lot * lot
                    if side == 'buy':
                        while quantity:
                            candidate_notional = price * quantity
                            candidate_cost = candidate_notional * (sum(rates.values())
                                + rates['impact'] * stress * candidate_notional / item['adv'])
                            if cash >= candidate_notional + candidate_cost:
                                break
                            quantity -= lot
                    if quantity:
                        status, reason = 'DEFINITE', 'certified opening volume'
                    else:
                        status, reason = 'NOT_EXECUTABLE', 'capacity, cash, inventory or volume'
            if quantity:
                notional = price * quantity
                participation = notional / item['adv']
                charges = {k: notional * v for k, v in rates.items()}
                charges['impact'] += notional * rates['impact'] * stress * participation
                total = sum(charges.values())
                if side == 'buy':
                    if cash < notional + total:
                        raise ValueError('cost-adjusted cash shortfall')
                    cash -= notional + total
                    positions.setdefault(entity, []).append((quantity, trading_date))
                else:
                    if total > notional:
                        raise ValueError('modeled charges exceed sale proceeds')
                    cash += notional - total
                    remaining = quantity; kept = []
                    for held, acquired in positions.get(entity, []):
                        take = min(held, remaining) if sellable(acquired, trading_date, rule['t_plus_sessions']) else 0
                        remaining -= take
                        if held != take:
                            kept.append((held - take, acquired))
                    if remaining:
                        raise ValueError('inventory conservation failure')
                    positions[entity] = kept
                _account(cash, positions, marks)
                item['remaining'] -= quantity
                used_volume[entity] = used_volume.get(entity, 0) + quantity
                used_notional[entity] = used_notional.get(entity, Decimal(0)) + notional
                gross = (mark - price) * quantity * (1 if side == 'buy' else -1)
                bridge = {'gross': str(gross), **{k: str(v) for k, v in charges.items()},
                          'net': str(gross - total)}
                fills.append(dict(entity=entity, side=side, quantity=quantity, reference_price=str(price),
                                  reference_notional=str(notional), fill_at=stamp, cost_bridge=bridge,
                                  participation=str(participation)))
            decisions.append(dict(entity=entity, side=side, decision_at=_iso(order['decision_at']),
                                  signal_at=_iso(order['signal_at']), order_created_at=_iso(order['order_created_at']),
                                  first_executable_at=item['first_executable_at'], fill_at=stamp if quantity else None,
                                  status=status, reason=reason, filled_quantity=quantity,
                                  unfilled_quantity=item['remaining']))
        value, nav = _account(cash, positions, marks)
        navs.append(dict(at=stamp, cash=str(cash), positions_value=str(value), nav=str(nav),
                         positions={e: sum(q for q, _ in lots) for e, lots in sorted(positions.items())}))
    return dict(versions=versions, decisions=decisions, fills=fills, actions=actions,
                ledger=navs, remaining=[p['remaining'] for p in pending],
                turnover=str(sum(_d(f['reference_notional']) for f in fills) / capital),
                target_capital=str(capital), assurance='SYNTHETIC_ONLY')
