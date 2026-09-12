# US6 T065 evidence — bounded source captures

Run over real temporary regular, hardlink, FIFO and rewritten files at a
16-byte limit.  The transcript records only outcomes and sizes, never payload
bytes.

```text
regular: status=permitted size=13 bytes_published=True provenance=None reason=None
hardlink: status=unsafe size=None bytes_published=False provenance=None reason=source is a hardlink alias
fifo: status=unsafe size=None bytes_published=False provenance=None reason=source is not an ordinary regular file
oversized: status=oversized size=17 bytes_published=False provenance=None reason=source is larger than the supplied byte limit
oversize-rewrite: status=unstable size=5 bytes_published=False provenance=changed reason=source changed between observations
unstable: status=unstable size=15 bytes_published=False provenance=changed reason=source changed between observations
```
