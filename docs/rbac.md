# RBAC and tenant access

Project Luvcraft uses Supabase Auth for identity verification and the application
database for authorization. Google Workspace, Microsoft Entra, and future SAML
providers can be enabled in Supabase without changing the RBAC data model.

## Authorization model

- `admin`: global access plus user, brand-domain, API-key, and audit governance.
- `analyst`: global operational access across brands, without user governance.
- `client`: read/write access limited to the assigned brand.
- `viewer`: read-only access to the assigned brand, or public demo runs when no
  brand is assigned.

`research_runs.target_brand_id` is the tenant boundary. `created_by` is retained
for attribution and must not be used as the access-control boundary.

## Required configuration

Backend environment:

```dotenv
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_JWT_SECRET=your-jwt-secret
INTERNAL_EMAIL_DOMAINS=pluto.studio,projectpluto.studio
RBAC_ADMIN_EMAILS=owner@pluto.studio
COOKIE_SECURE=true
```

Frontend environment:

```dotenv
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
NEXT_PUBLIC_API_URL=https://api.example.com
```

`RBAC_ADMIN_EMAILS` is an explicit bootstrap allowlist. It should contain the
minimum number of trusted accounts and can be emptied after administrators have
been provisioned. A domain match never grants `admin`; internal domains grant
`analyst` only.

## Deployment order

1. Back up the database.
2. Configure the backend and frontend environment variables.
3. Run `alembic -c alembic.ini upgrade head`.
4. Seed at least one `brand_profiles` row and its `brand_domains` entries.
5. Sign in once using an email in `RBAC_ADMIN_EMAILS`.
6. Use Access Management to assign roles and brands to other profiles.
7. Review legacy research runs with `target_brand_id IS NULL`. They remain
   visible only to global roles until explicitly assigned or marked as demos.

## API authentication

Browser requests use the secure HTTPOnly Supabase session cookie. CLI and
machine clients can use either `Authorization: Bearer <supabase-jwt>` or
`X-API-KEY: pluto_live_...`.

API keys are returned once, stored only as SHA-256 hashes, and inherit the
owner's current role, brand, active status, and tenant restrictions.

## SSO progression

Enterprise SSO is an identity-provider enhancement, not a replacement for
RBAC. When Google Workspace, Entra ID, or SAML is enabled, Supabase continues to
issue the JWT and the backend continues to resolve the same `user_profiles`,
roles, brands, and authorization policies.
