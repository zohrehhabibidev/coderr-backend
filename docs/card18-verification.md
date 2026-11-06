# Card 18: profile PATCH verification

Verified on 2026-11-06. Scope: PATCH /api/profile/{user_id}/ only.

## Implementation

- Existing RetrieveUpdateAPIView and User-ID lookup retained.
- Token authentication required; object permission permits GET for any
  authenticated user and PATCH only for the related User owner, for both roles.
- Writable: first_name, last_name, email, location, tel, description,
  working_hours, file. user, username, type, created_at are read-only; DRF
  ignores supplied read-only/unknown fields.
- Related User fields use source; validated supplied User values and Profile
  values are saved inside one database transaction. Omitted fields survive.
- Existing 12-field response order, User.date_joined timestamp, empty strings,
  and DRF image URL representation remain unchanged.
- ImageField and existing profiles/ storage path retained; multipart supported.
  No additional upload policy, dependency, model or migration introduced.

## Evidence

- manage.py check: no issues.
- Profile PATCH tests: 12/12 passed. Existing GET tests: 9/9 preserved;
  the old PATCH-disabled test was replaced by Card 18 behavior tests.
- Complete suite: 45/45 passed, including registration and login.
- Tests cover both owner roles, persistence in both models, exact ordered
  schema, partial/empty updates, protected fields, User/Profile ID mismatch,
  401/403/404, missing profiles, validation and transaction rollback.
- Postman CLI 1.73.0: local collection, 10 requests, 21 assertions, 0 failures.
  Executed against localhost:8765 with an isolated in-memory SQLite database,
  disposable customer/business users and filesystem image storage.
  Checked GET baseline, customer partial PATCH preserving all omitted values,
  business owner PATCH, 403, 401, 404, email, owner multipart image upload,
  forbidden multipart upload and JSON PATCH after upload.
- No existing local Postman project/environment was found. CLI cloud login was
  unavailable; the run used a task-specific local collection and did not publish
  results. Sandbox manifest access failed initially; execution outside the
  sandbox succeeded. Official PM collection/tests were not available or run.
- Clean-code review: explicit fields; focused methods at most 14 physical lines
  including decorators; changed Python lines at most 79 characters; no debug
  prints or dead code; git diff --check passed.

## Open acceptance questions

A2 remains unresolved: the written API contract and master checklist allow
email updates provisionally; reported teacher guidance prohibits them. This
implementation and tests follow the written contract. No authoritative
resolution has been obtained.

File upload is verified by automated multipart tests (isolated in-memory
storage) and a real Postman HTTP multipart request (filesystem storage).
These checks do not establish official PM acceptance. Trello remains In Arbeit
pending A2 clarification and official acceptance evidence.
