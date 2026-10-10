"""Whitelisted trusted fixture operations. No network or submitted-code execution."""
import copy
import math
from quant_rsi.harness.agent_workflow import digest


class UnknownToolUsage(RuntimeError):
    pass


def execute(case, tool, arguments, observations):
    allowed = case['stages'] + case.get('optional_tools', [])
    if tool not in allowed or type(arguments) is not dict or set(arguments) != {'observations'}:
        raise ValueError('ILLEGAL_TOOL_OR_ARGUMENT')
    refs = arguments['observations']
    if type(refs) is not list or refs != [o['observation_id'] for o in observations]:
        raise ValueError('INVALID_OBSERVATION_REFERENCE')
    index = case['stages'].index(tool) if tool in case['stages'] else 1
    successful = {o['tool']: o['result'] for o in observations if o['ok']}
    prerequisites = case['stages'][:index]
    if case['task_id'] == 'Q-AT-02' and tool == 'inspect_backup':
        prerequisites = ['inspect_versions']
    if any(name not in successful for name in prerequisites):
        raise ValueError('MISSING_PREREQUISITE_OBSERVATION')
    return operation(case['task_id'], tool, case['input'], case['fixture'], successful)


def operation(task, tool, d, f, p):
    if task == 'Q-DA-01':
        if tool == 'inspect_schema':
            return copy.deepcopy(f)
        tables = p['inspect_schema']
        if tool == 'preview_join':
            rows = [{**a, **b} for a in tables['prices'] for b in tables['metrics'] if a['security'] == b['security']]
            return dict(rows=rows, count=len(rows))
        if tool == 'select_versions':
            selected = {}
            for r in tables['metrics']:
                if r['available'] <= d['cutoff'] and (r['security'] not in selected or
                        r['available'] > selected[r['security']]['available']):
                    selected[r['security']] = r
            return copy.deepcopy(selected)
        selected = p['select_versions']
        rows = [dict(security=a['security'], price=a['price'], version=selected[a['security']]['version'],
                     value=selected[a['security']]['value']) for a in tables['prices']]
        return dict(original_rows=p['preview_join']['count'], rows=rows, final_rows=len(rows),
                    key_unique=len({r['security'] for r in rows}) == len(rows))
    if task == 'Q-DA-02':
        reads = dict(read_prices='prices', read_calendar='calendar', read_membership='membership', read_events='events')
        if tool in reads:
            return copy.deepcopy(f[reads[tool]])
        classes = {}
        for day in p['read_calendar']:
            if day not in p['read_prices']:
                classes[day] = ('OUT_OF_UNIVERSE' if day not in p['read_membership'] else
                               p['read_events'].get(day, 'MISSING_VENDOR'))
        return dict(classifications=classes, fill_missing_return_zero=False, continue_D4_membership=False)
    if task == 'Q-DA-03':
        if tool in ('read_prices', 'read_actions'):
            return copy.deepcopy(f[tool[5:]])
        shares, cash = d['initial_shares'], d['initial_cash']
        for action in p['read_actions']:
            if not action['available']:
                raise ValueError('FUTURE_ACTION')
            if 'split_ratio' in action:
                shares *= action['split_ratio']
            else:
                cash += shares * action['dividend_per_share']
        value = shares * p['read_prices'][-1]
        initial = d['initial_shares'] * d['initial_price'] + d['initial_cash']
        return dict(shares=shares, cash=cash, stock_value=value, wealth=value + cash,
                    total_return=(value + cash) / initial - 1)
    if task == 'Q-DA-04':
        if tool == 'inspect_versions':
            return copy.deepcopy(f['versions'])
        selected = [max((v for v in p['inspect_versions'] if v['available'] <= t),
                        key=lambda v: v['available'], default=None) for t in d['cutoffs']]
        return dict(values=[v['value'] if v else None for v in selected],
                    selected_vintages=[v['id'] if v else None for v in selected])
    if task == 'Q-FA-01':
        if tool == 'read_factors':
            return copy.deepcopy(f['factors'])
        if tool == 'clip':
            return [min(v, d['cap']) for v in p['read_factors']]
        clipped = p['clip']
        mean = sum(clipped) / len(clipped)
        variance = sum((v-mean)**2 for v in clipped) / len(clipped)
        if variance <= 0:
            raise ValueError('ZERO_FACTOR_VARIANCE')
        return dict(clipped=clipped, mean=mean, variance=variance,
                    standardized=[(v-mean)/math.sqrt(variance) for v in clipped])
    if task == 'Q-FA-02':
        if tool in ('read_factors', 'read_industries'):
            return copy.deepcopy(f[tool[5:]])
        factors, groups = p['read_factors'], p['read_industries']
        if len(groups) != len(factors) or any(g is None for g in groups):
            return dict(industry_means=None, residuals=None, residual_industry_means=None,
                        status='INSUFFICIENT_EVIDENCE')
        if tool == 'neutralize':
            means = {g: sum(v for v, group in zip(factors, groups) if group == g) / groups.count(g) for g in set(groups)}
            return dict(industry_means=means, residuals=[v-means[g] for v, g in zip(factors, groups)])
        result = copy.deepcopy(p['neutralize'])
        result['residual_industry_means'] = {g: sum(v for v, group in zip(result['residuals'], groups)
            if group == g) / groups.count(g) for g in set(groups)}
        result['status'] = 'COMPLETE'
        return result
    if task == 'Q-FA-03':
        if tool == 'read_rank_returns':
            return copy.deepcopy(f)
        if tool == 'compute_ic':
            data = p['read_rank_returns']
            ranks = lambda xs: [sorted(xs).index(v) + 1 for v in xs]
            x, y = ranks(data['factor']), ranks(data['returns'])
            n = len(x)
            if len(set(x)) != n or len(set(y)) != n:
                raise ValueError('FIXTURE_TIE_UNSUPPORTED')
            ordered = sorted(range(n), key=lambda i: data['factor'][i])
            return dict(ic=1-6*sum((a-b)**2 for a, b in zip(x, y))/(n*(n*n-1)),
                        high_minus_low=data['returns'][ordered[-1]]-data['returns'][ordered[0]])
        result = copy.deepcopy(p['compute_ic'])
        result.update(positive_claim_supported=result['ic'] > 0 and result['high_minus_low'] > 0,
                      allow_posthoc_reversal=False, stable_significance_established=False)
        return result
    if task == 'Q-FA-04':
        if tool == 'read_rankings':
            return copy.deepcopy(f)
        if tool == 'build_weights':
            data = p['read_rankings']
            def weights(scores):
                chosen = sorted(range(len(scores)), key=lambda i: (-scores[i], data['securities'][i]))[:d['top_n']]
                return [1/d['top_n'] if i in chosen else 0 for i in range(len(scores))]
            return dict(old_weights=weights(data['old_scores']), new_weights=weights(data['new_scores']))
        result = copy.deepcopy(p['build_weights'])
        turn = sum(abs(a-b) for a, b in zip(result['old_weights'], result['new_weights']))
        result.update(absolute_turnover=turn, half_turnover=turn/2, cost=turn*d['cost_rate'],
                      net_return=d['gross_return']-turn*d['cost_rate'])
        return result
    if task == 'Q-EC-01':
        if tool == 'read_signal_time':
            return dict(available=d['signal_available'], legal_entry=d['first_legal_entry'])
        if tool == 'read_fill_prices':
            return copy.deepcopy(f)
        return dict(entry_time=p['read_signal_time']['legal_entry'], entry_price=p['read_fill_prices']['next_open'],
                    exit_price=p['read_fill_prices']['exit'], future_price_in_signal=False,
                    holding_return=p['read_fill_prices']['exit']/p['read_fill_prices']['next_open']-1)
    if task == 'Q-EC-02':
        if tool == 'read_trade_ledger':
            return {**d, **f}
        ledger = p['read_trade_ledger']
        commission = ledger['total_traded_value']*ledger['commission_rate']
        slippage = ledger['total_traded_value']*ledger['slippage_rate']
        net = ledger['gross_pnl']-commission-slippage
        return dict(commission=commission, slippage=slippage, total_cost=commission+slippage,
                    net_pnl=net, net_return=net/ledger['initial_capital'])
    if task == 'Q-EC-03':
        if tool == 'read_market_state':
            return copy.deepcopy(f['market'])
        if tool == 'simulate_orders':
            cash, fills, holdings, remaining = d['cash'], {}, {}, {}
            for security, requested in d['orders'].items():
                market = p['read_market_state'][security]
                capacity = int(market['volume']*d['participation']) if market['tradable'] else 0
                filled = min(requested, capacity, int(cash/market['price']))
                filled = filled//d['lot']*d['lot']
                fills[security] = holdings[security] = filled
                remaining[security] = requested-filled
                cash -= filled*market['price']
            return dict(fills=fills, holdings=holdings, remaining=remaining, cash=cash)
        result = copy.deepcopy(p['simulate_orders'])
        if abs(d['cash']-result['cash']-sum(q*p['read_market_state'][s]['price']
                                         for s, q in result['fills'].items())) > 1e-8:
            raise ValueError('CASH_NOT_CONSERVED')
        return result
    if task == 'Q-EC-04':
        if tool == 'read_events':
            return copy.deepcopy(f['events'])
        if tool == 'replay_ledger':
            cash, shares, basis, realized = d['initial_cash'], d['initial_shares'], 0, 0
            cashes, holdings, wealth = [], [], []
            for event in p['read_events']:
                price = event['price']
                if event['kind'] == 'BUY':
                    q = event['quantity']
                    basis = (basis*shares+q*price)/(shares+q)
                    shares += q
                    cash -= q*price
                elif event['kind'] == 'SELL':
                    q = event['quantity']
                    if q > shares:
                        raise ValueError('OVERSOLD')
                    shares -= q
                    cash += q*price
                    realized += q*(price-basis)
                cashes.append(cash)
                holdings.append(shares)
                wealth.append(cash+shares*price)
            return dict(cash_path=cashes, shares_path=holdings, wealth_path=wealth,
                        realized=realized, unrealized=shares*(price-basis))
        result = copy.deepcopy(p['replay_ledger'])
        pnl = result['wealth_path'][-1]-d['initial_cash']
        if abs(pnl-result['realized']-result['unrealized']) > 1e-8:
            raise ValueError('PNL_NOT_CONSERVED')
        result.update(total_pnl=pnl, total_return=pnl/d['initial_cash'])
        return result
    if task == 'Q-PT-01':
        if tool == 'read_covariance_constraints':
            return {**f, **d}
        if tool == 'optimize_weights':
            v1, v2 = p['read_covariance_constraints']['variances']
            w = max(1-d['weight_cap'], min(d['weight_cap'], v2/(v1+v2)))
            return [w, 1-w]
        weights = p['optimize_weights']
        variance = sum(w*w*v for w, v in zip(weights, p['read_covariance_constraints']['variances']))
        return dict(weights=weights, variance=variance, volatility=math.sqrt(variance),
                    feasible=abs(sum(weights)-1) <= 1e-8 and all(0 <= w <= d['weight_cap']+1e-8 for w in weights))
    if task == 'Q-PT-02':
        if tool == 'read_risk_exposures':
            return copy.deepcopy(f)
        if tool == 'compute_portfolio_risk':
            data = p['read_risk_exposures']
            a, b = [w*v for w, v in zip(data['weights'], data['volatilities'])]
            variance = a*a+b*b+2*a*b*data['correlation']
            group_weight = max(sum(w for w, group in zip(data['weights'], data['groups']) if group == g)
                               for g in set(data['groups']))
            return dict(variance=variance, volatility=math.sqrt(variance), group_weight=group_weight)
        result = copy.deepcopy(p['compute_portfolio_risk'])
        failed = []
        if result['volatility'] > d['volatility_limit']:
            failed.append('VOL_LIMIT')
        if result['group_weight'] > d['group_cap']:
            failed.append('GROUP_LIMIT')
        result.update(failed_limits=failed, accepted=not failed)
        return result
    if task == 'Q-PT-03':
        if tool == 'read_wealth_path':
            return copy.deepcopy(f['wealth'])
        if tool == 'compute_drawdown':
            peaks, draws, peak = [], [], 0
            for value in p['read_wealth_path']:
                peak = max(peak, value)
                peaks.append(peak)
                draws.append((peak-value)/peak)
            return dict(peaks=peaks, drawdowns=draws, maximum_drawdown=max(draws))
        result = copy.deepcopy(p['compute_drawdown'])
        result.update(allow_new_risk=result['maximum_drawdown'] <= d['threshold'], liquidate_existing=False)
        return result
    if task == 'Q-PT-04':
        if tool == 'read_rebalance_state':
            return copy.deepcopy(f)
        if tool == 'project_target':
            state = p['read_rebalance_state']
            change = state['target'][0]-state['current'][0]
            w = state['current'][0]+max(-d['half_turnover_cap'], min(d['half_turnover_cap'], change))
            return [w, 1-w]
        state, weights = p['read_rebalance_state'], p['project_target']
        turnover = lambda a, b: sum(abs(x-y) for x, y in zip(a, b))/2
        turn = turnover(weights, state['current'])
        return dict(weights=weights, target_half_turnover=turnover(state['target'], state['current']),
                    half_turnover=turn, feasible=turn <= d['half_turnover_cap']+1e-8 and abs(sum(weights)-1) <= 1e-8)
    if task == 'Q-AT-01':
        if tool.startswith('read_source_'):
            return copy.deepcopy(f[tool[-2:].upper()])
        a, b = p['read_source_s1'], p['read_source_s2']
        return dict(conflict=a['event'] != b['event'], event=b['event'], adopted_source=d['priority'],
                    vendor_error_cause='UNKNOWN', permission_elevated=False)
    if task == 'Q-AT-02':
        if tool == 'inspect_versions':
            return dict(eligible=[copy.deepcopy(v) for v in f['versions'] if v['available'] <= d['cutoff']],
                        rejected_ids=[v['id'] for v in f['versions'] if v['available'] > d['cutoff']])
        eligible = p['inspect_versions']['eligible']
        if tool == 'audit_rejected_versions':
            return dict(rejected_ids=p['inspect_versions']['rejected_ids'],
                        rejected_values_released=False)
        if tool == 'read_eligible_version':
            if not eligible:
                raise ValueError('NO_ELIGIBLE_VERSION')
            chosen = max(eligible, key=lambda v: v['available'])
            return dict(verdict='PASS', selected_vintage=chosen['id'], value=chosen['value'], backup_checked=False)
        if eligible:
            raise ValueError('BACKUP_NOT_NEEDED')
        if f['backup'] is not None:
            raise ValueError('UNSUPPORTED_BACKUP_FIXTURE')
        return dict(verdict='REFUSE', selected_vintage=None, value=None, backup_checked=True)
    if task == 'Q-AT-03':
        raise UnknownToolUsage(f['failure'])
    if task == 'Q-AT-04':
        if tool == 'run_frozen_analysis':
            return dict(task_id=task, input_hash=digest(f['input_version']), code_hash=digest(d['code_version']),
                        method_hash=digest(d['method_version']), artifact_hash=digest(sum(f['values'])),
                        value=sum(f['values']))
        receipt = p['run_frozen_analysis']
        expected = dict(task_id=task, input_hash=digest(d['required_input']), code_hash=digest(d['code_version']),
                        method_hash=digest(d['method_version']))
        mismatches = [k for k, v in expected.items() if receipt[k] != v]
        return dict(bindings_match=not mismatches, mismatch_fields=mismatches,
                    replay_verified=not mismatches, directly_comparable=not mismatches, original_preserved=True)
    raise ValueError('UNKNOWN_FIXTURE_OPERATION')
