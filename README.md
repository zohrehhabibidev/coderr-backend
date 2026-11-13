# Coderr Backend

## Description

Coderr is a service marketplace where business users publish offers with three service packages and customers purchase a selected package. This backend provides a Django REST Framework API for registration, login, profiles, offers, orders, reviews, and platform statistics. Django Admin provides a separate management interface.

My contribution is the backend. The frontend was provided by **Developer Akademie** and is maintained separately: [provided Coderr frontend](https://github.com/Developer-Akademie-Backendkurs/project.Coderr).

The backend runs independently; no frontend installation is required to develop or test the API.

## Requirements

- Python **3.12 or later**, with `pip` and `venv`.
- Git and internet access for cloning and dependency installation.
- PowerShell on Windows, or Bash/Zsh on macOS/Linux.
- Write access to the project directory for SQLite and uploaded media.

Exact versions in `requirements.txt`:

| Dependency | Version | Purpose |
| --- | --- | --- |
| Django | 6.1.2 | Application framework, ORM, migrations, Admin |
| djangorestframework | 3.18.3 | API views, serializers, permissions, token authentication |
| Pillow | 13.0.0 | Image handling for profile and offer uploads |
| python-dotenv | 1.2.4 | Local environment configuration |
| asgiref | 3.13.0 | ASGI support |
| sqlparse | 0.6.0 | SQL parsing dependency |
| tzdata | 2026.5 | Time-zone data |

SQLite is configured locally; no separate database server is required. Tests use Django's test runner and DRF testing tools; pytest is not required.

## Installation

Follow these sections in order. After cloning, run commands from the repository root containing `manage.py` and `requirements.txt`.

### Windows

Open PowerShell:

```powershell
git clone https://github.com/zohrehhabibidev/coderr-backend.git
cd coderr-backend
py --version
```

Ensure the selected interpreter meets the Python requirement. If the Python launcher is unavailable, use `python` after checking `python --version`.

### macOS / Linux

```bash
git clone https://github.com/zohrehhabibidev/coderr-backend.git
cd coderr-backend
python3 --version
```

Ensure `python3` meets the Python requirement. Some Linux distributions require separate system packages for `pip` and `venv` matching the selected Python version.

## Create Virtual Environment

Windows (PowerShell):

```powershell
py -m venv .venv
```

macOS / Linux:

```bash
python3 -m venv .venv
```

## Activate Virtual Environment

Windows (PowerShell):

```powershell
.\.venv\Scripts\Activate.ps1
```

If activation is blocked and device policy permits it, allow scripts for the current terminal session and retry:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Alternatively, replace `python` in subsequent commands with `.\.venv\Scripts\python.exe`; activation is unnecessary when invoking that interpreter directly.

macOS / Linux:

```bash
source .venv/bin/activate
```

After activation, `python` and `python -m pip` use the virtual environment. Activate it again in each new terminal. Use `deactivate` to leave it.

## Install Dependencies

With the virtual environment active:

```text
python -m pip install -r requirements.txt
```

## Environment Variables

Create `.env` beside `manage.py` from the tracked template. These copy commands are intended for a fresh checkout; preserve an existing `.env`.

Windows (PowerShell):

```powershell
Copy-Item .env.example .env
```

macOS / Linux:

```bash
cp .env.example .env
```

Generate a unique signing key locally:

```text
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Edit `.env` in a text editor, replacing the placeholder with the generated value. Keep the single quotes around the key to preserve special characters:

```dotenv
SECRET_KEY='replace-with-your-own-generated-secret-key'
DEBUG=True
```

Never publish the generated key. The committed `.env.example` currently contains only the `SECRET_KEY` placeholder: **add `DEBUG=True` explicitly for local development**.

| Variable | Actual settings behavior |
| --- | --- |
| `SECRET_KEY` | Required through `os.environ["SECRET_KEY"]`; no default. A missing variable prevents settings from loading. Use a nonempty, unique value. |
| `DEBUG` | Defaults to `False`. Whitespace is stripped and the value is lowercased; only `true` enables debug mode. |

`core/settings.py` loads the root `.env` through `python-dotenv`. Existing process environment variables take precedence. No database URL, database credentials, SMTP credentials, or other environment variables are read by the current settings.

`ALLOWED_HOSTS` is hardcoded to `[]`, not read from `.env`. With `DEBUG=True`, local development hosts such as `localhost` and `127.0.0.1` are permitted. Setting `DEBUG=False` alone does not configure production hosting.

## Run Migrations

```text
python manage.py migrate
```

This creates the local `db.sqlite3` database and applies committed migrations for the four project apps and Django's authentication, tokens, Admin, and sessions. Do not run `makemigrations` as a normal fresh-install step.

Use the committed migrations for installation. Back up existing databases before migration work; the order snapshot data migration cannot be reversed.

No seed command or fixture import is required to start the backend. A fresh database has no marketplace accounts, offers, orders, or reviews.

## Create Superuser

```text
python manage.py createsuperuser
```

Follow the prompts for username, email, and password. Coderr uses Django's standard username-based `User`. Sign in to Admin with the chosen username and password; there are no bundled administrator credentials.

`createsuperuser` does not automatically create a customer/business `Profile`. Register marketplace accounts through the API, or deliberately create the corresponding profile in Admin. Staff status and marketplace role are separate: staff access alone does not grant customer/business API actions.

## Start Development Server

```text
python manage.py runserver
```

The default address is `http://127.0.0.1:8000/`.

- Admin: `http://127.0.0.1:8000/admin/`
- Public offer list: `http://127.0.0.1:8000/api/offers/`
- Public statistics: `http://127.0.0.1:8000/api/base-info/`
- Registration: `http://127.0.0.1:8000/api/registration/` (POST)
- Login: `http://127.0.0.1:8000/api/login/` (POST)

There is no application homepage at `/` or API index at `/api/`. Opening a browser URL sends GET; use an API client for registration, login, and writes. Stop the server with `Ctrl+C`.

## Project Structure

```text
coderr-backend/
|-- manage.py
|-- requirements.txt
|-- README.md
|-- .env.example
|-- .gitignore
|-- core/                  # Settings, central URLs, ASGI and WSGI
|-- auth_app/              # Profile linked one-to-one to Django User
|-- offers_app/            # Offer and OfferDetail models
|-- orders_app/            # Order model with purchased-term snapshots
`-- reviews_app/           # Review model and platform statistics API
```

Each project app contains `api/` (views, serializers, URLs, permissions), `migrations/`, `tests/`, and model/Admin configuration. `offers_app/api/` also contains filtering and pagination modules. Central routing includes all app APIs under `/api/`.

Setup creates `.venv/`, `.env`, and `db.sqlite3`; uploads are stored in `media/`. These local files/directories are ignored by Git.

## Authentication

The API uses DRF `TokenAuthentication` with `rest_framework.authtoken`. Authenticated requests require:

```http
Authorization: Token <token>
```

Replace `<token>` with the value returned by registration or login. Keep tokens private. Django Admin uses session authentication separately; an Admin browser login does not authenticate API requests.

Send JSON with `Content-Type: application/json`. Registration requires:

```json
{
  "username": "example_customer",
  "email": "customer@example.com",
  "password": "replace-with-a-strong-private-password",
  "repeated_password": "replace-with-a-strong-private-password",
  "type": "customer"
}
```

Use `"type": "business"` for a provider account. Registration creates the user, profile, and token atomically and returns HTTP 201. Login accepts:

```json
{
  "username": "example_customer",
  "password": "replace-with-a-strong-private-password"
}
```

Login returns HTTP 200 and creates or reuses the user's token. Both responses contain exactly `token`, `username`, `email`, and `user_id`. Password fields are not returned. No logout or token-refresh endpoint is defined.

### Customer and Business Roles

- A `customer` can place orders and create reviews of business users.
- A `business` can create offers and update the status of orders assigned to that business.
- Any authenticated user can read profiles, individual offers/packages, reviews, and business order counts. Order lists include only orders where the requester is the customer or business participant.
- Owners can update their profiles/offers and delete their offers. Review authors can update/delete their own reviews.
- Only staff (`is_staff=True`) can delete orders. Staff status does not bypass offer/review ownership rules.

Profile completion is not a prerequisite for authorized marketplace actions. Profile detail paths use the **user ID**, not the separate profile record ID. Profile updates support `first_name`, `last_name`, `file`, `location`, `tel`, `description`, `working_hours`, and `email`; identity, username, role, and creation timestamp are read-only. Unset profile text fields return empty strings.

## API Endpoints

The table covers all **23 documented method/path combinations**. IDs in braces are placeholders for existing integer IDs; retain trailing slashes.

“Public” means no token is required. All other rows require `Authorization: Token <token>` and the stated access rules. The status column shows the normal success response.

| Method | Endpoint | Purpose and access | Success |
| --- | --- | --- | --- |
| POST | `/api/registration/` | Public; create a customer/business account. | 201 |
| POST | `/api/login/` | Public; authenticate with username/password. | 200 |
| GET | `/api/profile/{pk}/` | Authenticated; retrieve a profile by user ID. | 200 |
| PATCH | `/api/profile/{pk}/` | Profile owner; partially update profile information. | 200 |
| GET | `/api/profiles/business/` | Authenticated; list business profiles. | 200 |
| GET | `/api/profiles/customer/` | Authenticated; list customer profiles. | 200 |
| GET | `/api/offers/` | Public; search, filter, order, and paginate offers. | 200 |
| POST | `/api/offers/` | Business only; create an offer with three packages. | 201 |
| GET | `/api/offers/{id}/` | Authenticated; retrieve an offer and package links. | 200 |
| PATCH | `/api/offers/{id}/` | Offer owner; partially update metadata/packages. | 200 |
| DELETE | `/api/offers/{id}/` | Offer owner; delete offer and its packages. | 204 |
| GET | `/api/offerdetails/{id}/` | Authenticated; retrieve one complete package. | 200 |
| GET | `/api/orders/` | Authenticated; list the requester's customer/business orders. | 200 |
| POST | `/api/orders/` | Customer only; purchase a selected package. | 201 |
| PATCH | `/api/orders/{id}/` | Assigned business with business profile; update status only. | 200 |
| DELETE | `/api/orders/{id}/` | Staff only; delete an order. | 204 |
| GET | `/api/order-count/{business_user_id}/` | Authenticated; count the business's in-progress orders. | 200 |
| GET | `/api/completed-order-count/{business_user_id}/` | Authenticated; count the business's completed orders. | 200 |
| GET | `/api/reviews/` | Authenticated; list/filter/order reviews. | 200 |
| POST | `/api/reviews/` | Customer only; create one review per business user. | 201 |
| PATCH | `/api/reviews/{id}/` | Review author; update rating/description only. | 200 |
| DELETE | `/api/reviews/{id}/` | Review author; delete a review. | 204 |
| GET | `/api/base-info/` | Public; retrieve platform statistics. | 200 |

Successful DELETE responses have no body. Authentication failures use 401; insufficient role/ownership uses 403; missing resources use 404; invalid input generally uses 400. No single-order GET or single-review GET is implemented. No explicit API throttling is configured.

### Offers and Three Packages

Offer creation accepts `title`, optional `image`, `description`, and exactly three `details`, one of each `offer_type`: `basic`, `standard`, `premium`. Each package contains `title`, `revisions`, `delivery_time_in_days`, `price`, `features` (an array of strings), and `offer_type`. Ownership comes from the authenticated business user.

Package prices use decimal storage with two decimal places and are serialized as JSON numbers. Offer creation and PATCH return full nested package data with IDs. PATCH identifies packages by `offer_type`, preserves IDs and omitted fields/packages, and rejects unsupported update fields. For example:

```json
{
  "title": "Updated design service",
  "details": [{"offer_type": "basic", "price": 120}]
}
```

Offer listing uses `count`, `next`, `previous`, and `results`. Each result includes metadata, package links, `min_price`, `min_delivery_time`, and `user_details` (`first_name`, `last_name`, `username`). Individual offer retrieval omits `user_details`. The two minima are computed independently across packages. An absent offer image is `null`.

| Offer query parameter | Behavior |
| --- | --- |
| `creator_id` | Filter by offer owner's user ID. |
| `min_price` | Require the offer's minimum package price to be at least this value. |
| `max_delivery_time` | Require the offer's minimum package delivery time to be at most this value. |
| `search` | Search title and description through DRF SearchFilter. |
| `ordering` | `updated_at`, `-updated_at`, `min_price`, or `-min_price`; default `-updated_at`, with ascending primary-key tie-break. |
| `page` | DRF page-number selection. |
| `page_size` | Positive integer; default 10, capped at 100. |

Profile, order, and review lists return arrays without pagination wrappers.

### Orders

Create an order using only `{"offer_detail_id": 1}`, replacing `1` with an existing package ID. The customer comes from authentication; the business comes from the selected package's offer owner. Initial status is `in_progress`.

Responses include `id`, `customer_user`, `business_user`, `title`, `revisions`, `delivery_time_in_days`, `price`, `features`, `offer_type`, `status`, `created_at`, and `updated_at`.

Purchased terms are stored as a snapshot. Later package edits do not change the order's agreed terms. Deleting an offer removes its packages but preserves orders with a null package reference. Order participants are protected against deletion while referenced by orders.

Status PATCH requires `{"status": "completed"}` or another supported value: `in_progress`, `completed`, `cancelled`. Other fields are rejected. Only the assigned business may perform this update.

The counters return `{"order_count": 0}` for in-progress orders and `{"completed_order_count": 0}` for completed orders, using actual counts. Cancelled orders enter neither count. A missing user or a user without a business profile returns 404.

### Reviews and Statistics

Review creation accepts `business_user` (a business user ID), `rating`, and `description`. The authenticated customer becomes the reviewer. The implementation validates integer ratings from **1 to 5** and permits one review per reviewer/business pair. It does not require an existing or completed order.

Reviews contain `id`, `business_user`, `reviewer`, `rating`, `description`, `created_at`, and `updated_at`. PATCH accepts only `rating` and `description`; an empty PATCH preserves the review and its timestamp.

Review listing supports integer filters `business_user_id` and `reviewer_id`. Its optional `ordering` accepts exactly `updated_at` or `rating` (ascending). No default ordering is specified by the view.

`GET /api/base-info/` returns `review_count`, `average_rating`, `business_profile_count`, and `offer_count`. The average includes all reviews, is rounded to one decimal place, and is `0.0` when there are no reviews.

## Automated Tests and Django Checks

With dependencies installed and `.env` configured:

```text
python -B manage.py check
python -B -m pip check
python -B manage.py makemigrations --check --dry-run
python -B manage.py test
```

`makemigrations --check --dry-run` detects model/migration drift without writing migration files. Run a focused app suite when needed:

```text
python -B manage.py test auth_app
python -B manage.py test offers_app
python -B manage.py test orders_app
python -B manage.py test reviews_app
```

The test suite covers authentication, profiles and uploads, offers and packages, filtering and pagination, orders and snapshots, permissions, reviews, statistics, and migrations. Run it through `manage.py test`, which creates a separate test database.

## Verification

The Fresh Clone Test completed successfully on Windows with Python 3.14.6:

- Clean dependency installation and SQLite migrations succeeded.
- Django and dependency checks passed.
- All 418 automated tests passed in 17.690 seconds.
- The development server, Django Admin, and public API smoke tests succeeded.

## Important Notes

### Security and Configuration

- This configuration is for local development. Production needs separate host, HTTPS, secret management, static/media serving, and deployment configuration; do not deploy with `DEBUG=True` or Django's development server.
- The current dependency list/settings include no CORS package or middleware. A browser frontend served from another origin requires separate integration configuration. Backend use through an API client is independent of that work.
- Keep `.env`, keys, passwords, API tokens, the SQLite database, virtual environments, and uploaded personal data out of commits. `.gitignore` excludes local secrets, databases, and media.
- Django's password validators are configured, but the registration serializer does not call Django's password validation API. It checks matching passwords and uses `create_user` for password hashing; do not assume registration enforces all configured password-strength rules.
- Locale/time settings are `en-us`, UTC, and time-zone-aware datetimes. No external email-service credentials are required; the configured mailer uses the console backend.

### Media Files

Profile pictures use `media/profiles/`; offer images use `media/offers/`. Files are stored beneath `MEDIA_ROOT = BASE_DIR / "media"` and exposed at `/media/` by the development URL configuration only when `DEBUG=True`. Use multipart form data for profile image uploads through `file`; JSON examples containing image paths do not upload binary files.

Uploaded media is not bundled in a fresh clone. Preserve the database and associated media together when backing up an existing installation. No custom upload-size policy is configured in the application; production file validation and serving need separate review.

## Credits and Author

- **Backend author:** [Zohreh Habibi](https://github.com/zohrehhabibidev) — Django/DRF backend implementation for Coderr.
- **Frontend:** supplied by [Developer Akademie](https://github.com/Developer-Akademie-Backendkurs/project.Coderr). The supplied frontend is not my work and is maintained outside this backend repository.
- **Backend repository:** [coderr-backend](https://github.com/zohrehhabibidev/coderr-backend).
