This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3101](http://localhost:3101) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
## Runtime deployment

- Container image: `legal-search/frontend/Dockerfile`
- Required runtime env var: `NEXT_PUBLIC_API_URL`
- Optional runtime env var: `NEXT_PUBLIC_CONTROL_PANEL_URL` (base URL for the control-plane entrypoint when the user is allowed to see it)
- Optional runtime env var: `NEXT_PUBLIC_DEFAULT_UI_PROFILE` (`admin` | `standard`) — default when no `evidara-ui-profile` cookie is present; unset behaves like `admin` for backward compatibility
- Session integration: set the `evidara-ui-profile` cookie to `standard` to hide the control panel link for non-operator users even when `NEXT_PUBLIC_CONTROL_PANEL_URL` is configured
- Cloud Run service key: `legal-search-frontend` (dev/staging tfvars)
