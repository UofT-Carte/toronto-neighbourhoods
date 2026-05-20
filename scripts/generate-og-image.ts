import { chromium } from 'playwright';
import sharp from 'sharp';
import fs from 'fs';
import path from 'path';

const WIDTH = 1200;
const HEIGHT = 630;
const BAR_HEIGHT = 150;

const svgOverlay = `<svg xmlns="http://www.w3.org/2000/svg" width="${WIDTH}" height="${HEIGHT}">
  <rect x="0" y="${HEIGHT - BAR_HEIGHT}" width="${WIDTH}" height="${BAR_HEIGHT}" fill="#1E3765"/>
  <text
    x="40" y="${HEIGHT - BAR_HEIGHT + 65}"
    font-family="Georgia, serif"
    font-size="44"
    font-weight="bold"
    fill="white"
  >Draw Your Toronto Neighbourhood</text>
  <text
    x="40" y="${HEIGHT - BAR_HEIGHT + 115}"
    font-family="system-ui, sans-serif"
    font-size="24"
    fill="#6FC7EA"
  >carte.utoronto.ca/neighbourhoods</text>
</svg>`;

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  await page.setViewportSize({ width: WIDTH, height: HEIGHT });
  await page.goto('http://localhost:3000/neighbourhoods/');

  // Wait for the map canvas to appear (MapLibre initialises async)
  await page.waitForSelector('.maplibregl-canvas');

  // Hide the sidebar so only the map fills the viewport
  await page.evaluate(() => {
    const root = document.querySelector('#root > div') as HTMLElement | null;
    if (!root) throw new Error('#root > div not found');
    const sidebar = root.firstElementChild as HTMLElement | null;
    if (!sidebar) throw new Error('sidebar element not found');
    sidebar.style.display = 'none';
  });

  // Wait for tile network requests to settle
  await page.waitForLoadState('networkidle');

  const screenshotBuffer = await page.screenshot();
  await browser.close();

  const outputPath = path.resolve('public/og-image.png');
  fs.mkdirSync('public', { recursive: true });

  await sharp(screenshotBuffer)
    .resize(WIDTH, HEIGHT)
    .composite([{ input: Buffer.from(svgOverlay), top: 0, left: 0 }])
    .png()
    .toFile(outputPath);

  console.log(`✓ Written ${WIDTH}×${HEIGHT} image to ${outputPath}`);
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
