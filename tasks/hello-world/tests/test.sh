#!/bin/bash
cd /logs/solution

# Run the solution
python3 -c "
import sys, json, os
sys.path.insert(0, '.')
exec(open('solve.py').read())

# Test
try:
    result = hello()
    if result == 'Hello, World!':
        reward = {'reward': 1.0, 'accuracy': 1.0, 'passed': True}
    else:
        reward = {'reward': 0.0, 'accuracy': 0.0, 'passed': False, 'error': f'Got {result}'}
except Exception as e:
    reward = {'reward': 0.0, 'accuracy': 0.0, 'passed': False, 'error': str(e)}

# Write reward to /logs/verifier/
os.makedirs('/logs/verifier', exist_ok=True)
with open('/logs/verifier/reward.json', 'w') as f:
    json.dump(reward, f, indent=2)

print(json.dumps(reward))
"
