import "./globals.css";

export const metadata = {
  title: "Atlante BI",
  description: "AI-powered BI foundation for Italian SMBs"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="it">
      <body>{children}</body>
    </html>
  );
}
