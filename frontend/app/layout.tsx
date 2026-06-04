import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "LossQ | AI Underwriting Platform",
    template: "%s | LossQ",
  },
  description:
    "LossQ is an AI underwriting intelligence platform for loss runs, renewal risk, carrier strategy, premium forecasting, and submission building.",
  applicationName: "LossQ",
  keywords: [
    "LossQ",
    "loss runs",
    "insurance underwriting",
    "renewal risk",
    "carrier submissions",
    "commercial insurance",
  ],
  authors: [{ name: "LossQ" }],
  creator: "LossQ",
  publisher: "LossQ",
  icons: {
    icon: "/favicon.ico",
    shortcut: "/favicon.ico",
    apple: "/lossq-logo-style2.png",
  },
  openGraph: {
    title: "LossQ | AI Underwriting Platform",
    description:
      "AI-powered loss run analysis, renewal risk scoring, carrier match, premium forecast, and submission intelligence.",
    siteName: "LossQ",
    images: [
      {
        url: "/lossq-logo-style2.png",
        width: 1200,
        height: 630,
        alt: "LossQ AI Underwriting Platform",
      },
    ],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "LossQ | AI Underwriting Platform",
    description:
      "AI-powered underwriting intelligence for brokers, carriers, and renewal strategy.",
    images: ["/lossq-logo-style2.png"],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}