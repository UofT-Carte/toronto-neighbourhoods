import express from 'express';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const PORT = 4321;

const app = express();

// Serve the app's map style so the dashboard map matches the site.
app.get('/map-style.json', (_req, res) => {
  res.sendFile(join(ROOT, 'src', 'assets', 'map-style.json'));
});

// Static dashboard assets (index.html, etc.)
app.use(express.static(__dirname));

app.listen(PORT, () => {
  console.log(`\n  Submissions dashboard running at http://localhost:${PORT}\n`);
});
