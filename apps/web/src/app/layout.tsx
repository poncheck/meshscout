import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MeshScout - Meshtastic Network Visualization",
  description: "Real-time visualization of the Meshtastic network with H3 hexagons",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
