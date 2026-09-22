import { defineConfig } from "vitepress";

const APP = "https://app-production-7810.up.railway.app";
const REPO = "https://github.com/TenureLP/tenure";

export default defineConfig({
  title: "Tenure",
  description:
    "Sell your Uniswap v4 position, lease it straight back, keep the fees, buy it back at a price fixed upfront. No loan, no liquidation, no oracle.",
  lang: "en",
  cleanUrls: true,
  lastUpdated: false,
  srcExclude: ["README.md"],
  // The site is dark only: it is the same product as the app, and the app is dark only.
  appearance: "force-dark",
  head: [
    ["link", { rel: "icon", type: "image/svg+xml", href: "/logo.svg" }],
    ["link", { rel: "preconnect", href: "https://fonts.googleapis.com" }],
    ["link", { rel: "preconnect", href: "https://fonts.gstatic.com", crossorigin: "" }],
    ["link", { rel: "stylesheet", href: "https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&display=swap" }],
    ["meta", { name: "theme-color", content: "#0A111D" }],
    ["meta", { property: "og:title", content: "Tenure docs" }],
    ["meta", { property: "og:description", content: "Sale-and-leaseback for Uniswap v4 positions on Robinhood Chain." }],
  ],
  themeConfig: {
    logo: "/logo.svg",
    siteTitle: "Tenure",
    nav: [
      { text: "Guide", link: "/guide/how-a-deal-works" },
      { text: "Contracts", link: "/contracts/lease-vault" },
      { text: "API", link: "/api/" },
      { text: "Testnet", link: "/guide/testnet" },
      { text: "Open the app", link: APP },
    ],
    sidebar: [
      {
        text: "Start here",
        items: [
          { text: "What Tenure is", link: "/" },
          { text: "How a deal works", link: "/guide/how-a-deal-works" },
          { text: "Testnet", link: "/guide/testnet" },
        ],
      },
      {
        text: "Guides",
        items: [
          { text: "Selling a position", link: "/guide/sellers" },
          { text: "Funding a deal", link: "/guide/financiers" },
          { text: "Builder codes", link: "/guide/builders" },
          { text: "Using the app", link: "/app/" },
        ],
      },
      {
        text: "Concepts",
        items: [
          { text: "Rent and how it accrues", link: "/concepts/rent" },
          { text: "The buyback rule", link: "/concepts/buyback" },
          { text: "Freezes", link: "/concepts/freezes" },
          { text: "What is guaranteed, and what is not", link: "/concepts/guarantees" },
        ],
      },
      {
        text: "Contracts",
        items: [
          { text: "LeaseVault reference", link: "/contracts/lease-vault" },
          { text: "Errors", link: "/contracts/errors" },
          { text: "Addresses", link: "/contracts/addresses" },
          { text: "Deploying", link: "/contracts/deploying" },
        ],
      },
      {
        text: "Valuation API",
        items: [
          { text: "Overview", link: "/api/" },
          { text: "Quotes", link: "/api/quotes" },
          { text: "Paying per request", link: "/api/payments" },
        ],
      },
      {
        text: "More",
        items: [{ text: "FAQ", link: "/faq" }],
      },
    ],
    socialLinks: [{ icon: "github", link: REPO }],
    search: { provider: "local" },
    editLink: { pattern: `${REPO}/edit/main/docs-site/:path`, text: "Edit this page" },
    outline: { level: [2, 3], label: "On this page" },
    footer: {
      message: "Prototype. Unaudited. Nothing here is financial advice.",
      copyright: "Contracts under the MIT licence (SPDX)",
    },
  },
});
