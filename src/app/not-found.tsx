import Link from "next/link";

/**
 * Global 404 page.
 *
 * Next.js renders this automatically for any unmatched route.
 * Replace the copy and style with your product's brand when forking.
 */
export default function NotFound(): React.ReactElement {
  return (
    <div className="flex flex-1 items-center justify-center px-6 py-24">
      <div className="text-center">
        <p className="text-muted-foreground text-sm font-semibold tracking-wider uppercase">404</p>
        <h1 className="text-foreground mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
          Page not found
        </h1>
        <p className="text-muted-foreground mt-4 text-base leading-7">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
        <div className="mt-8">
          <Link
            href="/"
            className="bg-primary text-primary-foreground hover:bg-primary/90 inline-flex h-10 items-center justify-center rounded-lg px-6 text-sm font-medium transition-colors"
          >
            Back to home
          </Link>
        </div>
      </div>
    </div>
  );
}
