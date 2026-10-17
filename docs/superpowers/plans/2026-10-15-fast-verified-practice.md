# Fast verified three-question practice repair

**Goal:** After self-assessment >= 7, prepare exactly three valid variations of the current method within 180 seconds, then require real answers before clearing the lesson.

**Evidence:** The supplied DuMate PDF has two pages but an undecodable ASCII85 content stream. The existing generator permits a 360-second operation plus model SDK retries. Empty stems are accepted by materials inputs. Skill currently routes high self-assessment into a different checkpoint before practice and permits an orchestration detour.

**Architecture:** Keep six MCP tools. Add source-driven generation to generate_practice_pdf, one deadline for generation, PDF verification and delivery, independently verified auxiliary-angle variations for the supplied case, and parallel bounded model requests for other supported topics. Keep legacy caller parameters and base64 responses compatible. Use an expiring capability URL and SHA-256 for reliable binary transfer in DuMate. Validate page streams and every expected stem before returning an artifact.

- [x] Reproduce blank input and corrupt PDF acceptance with regression tests.
- [x] Build and independently verify three auxiliary-angle variations, including range/sign reasoning and one reversed question.
- [x] Bound generic generation, disable SDK retries for practice, and stop incomplete sets from claiming success.
- [x] Reject blank question stems, verify rendered content streams, and add expiring checked download artifacts.
- [x] Add an atomic source-to-PDF path with a shared deadline under 180 seconds, preserving six tools.
- [x] Update teaching Skill: three variations test mastery; a self-rating alone never clears the lesson; use verified downloads and stop repeated tool retries.
- [x] Run targeted and complete pytest, reproduce a visible three-question student paper and separate answer pages, render and inspect them, and record real elapsed times.
- [x] Commit the repair, report deployment boundaries, and ask whether to push both GitHub and Gitee.

**Validation:** Real PDF parsing and text extraction; corruption/blank rejection; endpoint download hash round trip; expiry/traversal controls; bounded slow-provider test; all-three validity tests; prior audit regressions; visual page inspection; full pytest. Live DuMate latency can only be claimed after its server and installed Skill have been updated and observed.
