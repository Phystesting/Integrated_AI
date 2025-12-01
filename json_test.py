import json

# a Python object (dict):
x = [1,2,3]

# convert into JSON:
y = json.dumps(x)

# the result is a JSON string:
print(len(json.loads(y)))
