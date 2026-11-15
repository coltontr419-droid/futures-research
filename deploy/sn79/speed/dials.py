import re, sys
src = open(sys.argv[1]).read()
for m in re.finditer(r'"--(scoring\.(?:debeta|activity)[^"]*)"\s*,(.*?)\)\s*\n', src, re.S):
    name, body = m.group(1), m.group(2)
    d = re.search(r'default\s*=\s*([^,\n]+)', body); h = re.search(r'help\s*=\s*\(?((?:"[^"]*"\s*)+)', body)
    help_ = re.sub(r'"\s*"', "", h.group(1)).strip('" ') if h else ""
    print(f"{name} = {d.group(1).strip() if d else '?'} :: {help_[:230]}")
