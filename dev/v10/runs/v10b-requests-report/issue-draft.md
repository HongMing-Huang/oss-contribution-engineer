# Draft (from session evidence)

Query: Fix _encode_files detection for __getattr__-based file wrappers

Root cause facts:
- file detection in _encode_files: fp treated as content only if str/bytes/bytearray or _SupportsRead; otherwise the OBJECT ITSELF is passed as fdata
- guess_filename uses getattr(obj,name,None) — already duck-typed; the file-detection path above it is not

Proposed change:
- 2252ff8c Detect __getattr__-based file wrappers in _encode_files
