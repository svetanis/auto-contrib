# PR Title: fix(auth): resolve null pointer exception in login

## Description
This Pull Request resolves the intermittent `NullPointerException` that occurs when a user attempts to login with an expired session token.

## Changes Made
- Added a null check in `AuthenticationManager.java` before accessing the session token.
- Updated `LoginController.java` to gracefully return a `401 Unauthorized` instead of a `500 Server Error`.
- Authored new unit tests in `AuthenticationManagerTest.java` to reproduce the bug and verify the fix.

## Verification
- [x] All unit tests compile and pass via GitHub Actions.
- [x] Code formatting adheres to repository guidelines.
- [x] All `WIP:` debugging commits have been squashed into a single clean commit.
- [x] The commit is signed with the required Developer Certificate of Origin (DCO).

---
*Generated autonomously by `auto-contrib`*
