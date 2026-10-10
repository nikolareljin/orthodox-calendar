import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const dist = resolve(import.meta.dirname, "..", "dist");
const site = "https://nikolareljin.github.io/orthodox-calendar/";
const title = "Orthodox Calendar - Saints, Feasts and Readings";
const description = "Explore saints, feasts, fasting rules, readings and iCal feeds across Orthodox and Oriental Orthodox traditions.";
const image = `${site}og-image.png`;
const html = readFileSync(resolve(dist, "index.html"), "utf8");
const sitemap = readFileSync(resolve(dist, "sitemap.xml"), "utf8");

const expected = [
  ["<title>", title],
  ['name="description"', description],
  ['rel="canonical"', site],
  ['property="og:title"', title],
  ['property="og:description"', description],
  ['property="og:url"', site],
  ['property="og:image"', image],
  ['name="twitter:card"', "summary_large_image"],
  ['name="twitter:image"', image],
];

for (const [marker, value] of expected) {
  if (!html.includes(marker) || !html.includes(value)) {
    throw new Error(`Missing SEO value: ${marker}=${value}`);
  }
  if (html.split(marker).length - 1 !== 1) {
    throw new Error(`Expected exactly one ${marker} tag`);
  }
}

if (description.length > 160) {
  throw new Error(`Description is ${description.length} characters, maximum is 160`);
}

const jsonLd = html.match(/<script type="application\/ld\+json">(.*?)<\/script>/s);
if (!jsonLd) throw new Error("Missing JSON-LD");
const schema = JSON.parse(jsonLd[1]);
if (schema["@type"] !== "WebApplication" || schema.url !== site || schema.image !== image) {
  throw new Error("JSON-LD does not describe the published WebApplication");
}

if (sitemap !== `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url><loc>${site}</loc></url>\n</urlset>\n`) {
  throw new Error("sitemap.xml does not contain exactly the published root URL");
}

const png = readFileSync(resolve(dist, "og-image.png"));
if (png.readUInt32BE(16) !== 1200 || png.readUInt32BE(20) !== 630) {
  throw new Error("og-image.png must be 1200x630");
}

if (readFileSync(resolve(dist, "googlefb1695ee9a07673e.html"), "utf8").trim() !== "google-site-verification: googlefb1695ee9a07673e.html") {
  throw new Error("Google Search Console verification file has changed");
}

console.log("SEO checks passed.");
