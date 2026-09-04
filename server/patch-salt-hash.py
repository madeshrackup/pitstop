#!/usr/bin/env python3
"""Patch wfc-server nas/payload.go so salt hash matches stage1 v1 clients.

Stage1 v1 hashes the full query (including c,v,d,f,k,...) minus trailing &h=....
The stock integrated handler only hashed g+s, causing 20913 / Salt hash mismatch.
"""
from pathlib import Path

path = Path("nas/payload.go")
text = path.read_text(encoding="utf-8")
old = '''\t\t// Generate the salt hash
\t\tsaltHashData := "payload?g=" + query["g"][0] + "&s=" + query["s"][0]
'''
new = '''\t\t// Generate the salt hash (full query minus trailing &h=XXXXXXXX; stage1 v1)
\t\thashQuery := r.URL.RawQuery
\t\tif len(hashQuery) < 11 || hashQuery[len(hashQuery)-11:len(hashQuery)-8] != "&h=" {
\t\t\tlogging.Error(moduleName, "Invalid salt hash in query")
\t\t\treturn
\t\t}
\t\thashQuery = hashQuery[:len(hashQuery)-11]
\t\tsaltHashData := "payload?" + hashQuery
'''
if old not in text:
    raise SystemExit("expected salt hash block not found — upstream changed?")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("patched nas/payload.go salt hash for stage1 v1")
