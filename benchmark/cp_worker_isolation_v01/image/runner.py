"""Generic untrusted-code execution INSIDE the container; no Oracle or scoring."""
import copy
import json
import runpy


with open('/public/input.json', encoding='utf-8') as stream:
    packet = json.load(stream)
if packet['mode'] == 'probe':
    runpy.run_path('/submit/submission.py', run_name='__main__')
else:
    namespace = runpy.run_path('/submit/submission.py')
    retained, records = [], []
    for operation in packet['operations']:
        if 'mutate_previous' in operation:
            change = operation['mutate_previous']
            target = retained[change['index']]
            for key in change['path'][:-1]:
                target = target[key]
            target[change['path'][-1]] = change['value']
            continue
        args = copy.deepcopy(operation['args'])
        before = copy.deepcopy(args)
        try:
            value = namespace[operation['function']](*args)
            records.append(dict(value=copy.deepcopy(value), error=None, input_unchanged=args == before))
            retained.append(value)
        except Exception as exc:
            records.append(dict(value=None, error=type(exc).__name__, input_unchanged=args == before))
            retained.append(None)
    print(json.dumps(dict(records=records, retained=retained), allow_nan=False))
