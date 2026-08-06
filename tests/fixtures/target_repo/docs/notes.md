# Notes

A non-empty tracked file at a stable path, so read-scope nodes have an
`expected_artifacts` target that exists and satisfies the artifact check without
anything having to be written first.

Its counterpart — an artifact path that exists but is empty — is created by the
test that needs it, since an empty file cannot be committed to git and stay empty
in a way that reads as deliberate.
