# Root Cause

Known facts:
- file detection in _encode_files: fp treated as content only if str/bytes/bytearray or _SupportsRead; otherwise the OBJECT ITSELF is passed as fdata
- guess_filename uses getattr(obj,name,None) — already duck-typed; the file-detection path above it is not

Hypotheses:
- a wrapper with __getattr__ forwarding to an open file is a real file but fails str/bytes and _SupportsRead checks only if the inner attrs are not eagerly visible

Evidence:
- followed inherits class:src/requests/_types.py::_ValidatedRequest to answer: where is guess_filename defined and what does it accept?
- RED at base: TypeError bytes-like required, not LazyFile (urllib3 filepost body.write)
