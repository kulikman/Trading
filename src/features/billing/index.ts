/**
 * Billing feature — public API.
 *
 * Payment route handlers stay in `src/app/api/stripe/*` because they are
 * external HTTP entry points. Import billing UI through this barrel.
 */
export { BillingCard } from "./components/billing-card";
