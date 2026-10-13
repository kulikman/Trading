/**
 * Auth shell. Centers a card on the screen — keep it minimal so login,
 * signup, password-reset, and magic-link share a layout.
 */
export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <div className="bg-muted/30 flex flex-1 items-center justify-center px-4 py-12">
      <div className="border-border bg-card w-full max-w-md rounded-2xl border p-8 shadow-sm">
        {children}
      </div>
    </div>
  );
}
