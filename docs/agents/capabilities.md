# Client capabilities

The intent in each row is shared. A client either has an explicit binding or the
row reports that the binding is unavailable; there is no universal capability
API. A fallback is narrow and does not create authority.

| Job | Shared intent | Codex CLI binding | Claude Code binding | Absent-binding fallback |
| --- | --- | --- | --- | --- |
| ask | Raise a blocking question for the operator. | unavailable — narrow fallback: state the fork, options, and current work in the response. | unavailable — narrow fallback: state the fork, options, and current work in the response. | narrow fallback: wait only the already-bounded window, then continue on a safe path if one exists. |
| delegate | Give a bounded task to another worker. | unavailable — narrow fallback: draft the bounded task and scope, then ask for separately declared dispatch authority. | unavailable — narrow fallback: draft the bounded task and scope, then ask for separately declared dispatch authority. | narrow fallback: do not spawn work outside the operator-approved DAG. |
| recall | Retrieve durable cross-session memory. | unavailable — narrow fallback: use the current prompt and declared repository context. | unavailable — narrow fallback: use the current prompt and declared repository context. | narrow fallback: report memory as unavailable; never write or claim recall. |
| schedule | Queue or delay future work. | unavailable — narrow fallback: report the proposed schedule to the operator. | unavailable — narrow fallback: report the proposed schedule to the operator. | narrow fallback: leave scheduling to the declared Ergane workflow. |
| notify | Send a notification outside the current response. | unavailable — narrow fallback: include the notice in the current response. | unavailable — narrow fallback: include the notice in the current response. | narrow fallback: report that notification could not be delivered. |
| render | Present local output for human review. | unavailable — narrow fallback: use plain Markdown in the response. | unavailable — narrow fallback: use plain Markdown in the response. | narrow fallback: do not invent a client render API or open a browser. |
| stop | End the current run at a defined boundary. | unavailable as a shared client binding — narrow fallback: stop at the prompt's declared boundary. | unavailable as a shared client binding — narrow fallback: stop at the prompt's declared boundary. | narrow fallback: report remaining work and stop rather than blocking indefinitely. |
| publish | Make a repository change public. | unavailable — narrow fallback: prepare the proposed change, then request separately declared publication authority. | unavailable — narrow fallback: prepare the proposed change, then request separately declared publication authority. | narrow fallback: use only the declared Ergane landing path after authorization. |

Memory absence is a contract result, not a transient error to retry. It never
grants a node or an unattended run authority to create memory.
