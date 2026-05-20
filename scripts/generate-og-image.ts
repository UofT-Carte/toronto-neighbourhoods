import { chromium } from 'playwright';
import sharp from 'sharp';
import fs from 'fs';
import path from 'path';

const WIDTH = 1200;
const HEIGHT = 630;
const BAR_HEIGHT = 150;
const MAP_HEIGHT = HEIGHT - BAR_HEIGHT; // 480

const navyBarSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="${WIDTH}" height="${BAR_HEIGHT}">
  <rect width="${WIDTH}" height="${BAR_HEIGHT}" fill="#1E3765"/>
  <text
    x="40" y="65"
    font-family="Times New Roman, serif"
    font-size="44"
    font-weight="bold"
    fill="white"
  >Draw Your Toronto Neighbourhood</text>
  <text
    x="40" y="115"
    font-family="Arial, sans-serif"
    font-size="24"
    fill="#6FC7EA"
  >carte.utoronto.ca/neighbourhoods</text>
</svg>`;

async function main() {
  const root = path.resolve('.');

  const torontoGeoJson  = JSON.parse(fs.readFileSync(path.join(root, 'src/toronto.json'), 'utf-8'));
  const mapStyle        = JSON.parse(fs.readFileSync(path.join(root, 'src/assets/map-style.json'), 'utf-8'));
  const transitLines    = JSON.parse(fs.readFileSync(path.join(root, 'src/assets/toronto-data/current-lines.geo.json'), 'utf-8'));
  const transitStations = JSON.parse(fs.readFileSync(path.join(root, 'src/assets/toronto-data/current-stations.geo.json'), 'utf-8'));
  const parkPoints      = JSON.parse(fs.readFileSync(path.join(root, 'src/assets/toronto-data/park-points.geo.json'), 'utf-8'));

  // Polygon coordinates (lng, lat) used for the mask and boundary layers
  const torontoPolygon: [number, number][] = torontoGeoJson.coordinates[0];

  // Bounding box of the polygon — same calculation as TORONTO_FIT_BOUNDS in MapEditor
  const torontoBounds = torontoPolygon.reduce<[[number, number], [number, number]]>(
    ([[minLng, minLat], [maxLng, maxLat]], [lng, lat]) => [
      [Math.min(minLng, lng), Math.min(minLat, lat)],
      [Math.max(maxLng, lng), Math.max(maxLat, lat)],
    ],
    [[Infinity, Infinity], [-Infinity, -Infinity]]
  );

  // Attach data sources to the style object before passing to MapLibre
  mapStyle.sources['transit-lines']     = { type: 'geojson', data: transitLines };
  mapStyle.sources['transit-stations']  = { type: 'geojson', data: transitStations };
  mapStyle.sources['park-points']       = { type: 'geojson', data: parkPoints };
  mapStyle.sources['toronto-boundary']  = {
    type: 'geojson',
    data: { type: 'Feature', geometry: { type: 'LineString', coordinates: torontoPolygon } },
  };

  const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <script src="https://unpkg.com/maplibre-gl/dist/maplibre-gl.js"></script>
  <link href="https://unpkg.com/maplibre-gl/dist/maplibre-gl.css" rel="stylesheet" />
  <style>
    * { margin: 0; padding: 0; }
    html, body { width: ${WIDTH}px; height: ${MAP_HEIGHT}px; overflow: hidden; }
    #map { width: ${WIDTH}px; height: ${MAP_HEIGHT}px; position: relative; }
  </style>
</head>
<body>
  <div id="map"></div>
  <script>
    const torontoPolygon = ${JSON.stringify(torontoPolygon)};
    const torontoBounds  = ${JSON.stringify(torontoBounds)};

    const map = new maplibregl.Map({
      container: 'map',
      style: ${JSON.stringify(mapStyle)},
      center: [-79.3832, 43.6532],
      zoom: 11,
      bearing: 0,
      interactive: false,
      attributionControl: false,
    });

    map.on('load', () => {
      // Fit to Toronto bounds at bearing 0 (same zoom as the app), then rotate —
      // passing bearing to fitBounds lowers the zoom to fit rotated corners, which isn't what the app does
      map.fitBounds(torontoBounds, { padding: 20, bearing: 0, animate: false });
      map.setBearing(-17);

      // Canvas mask: white overlay with the Toronto polygon cut out
      const mapEl = document.getElementById('map');
      const maskCanvas = document.createElement('canvas');
      maskCanvas.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:1';
      maskCanvas.width  = ${WIDTH};
      maskCanvas.height = ${MAP_HEIGHT};
      mapEl.appendChild(maskCanvas);

      const drawMask = () => {
        const ctx = maskCanvas.getContext('2d');
        ctx.clearRect(0, 0, ${WIDTH}, ${MAP_HEIGHT});
        ctx.fillStyle = 'rgba(255,255,255,0.75)';
        ctx.fillRect(0, 0, ${WIDTH}, ${MAP_HEIGHT});
        ctx.globalCompositeOperation = 'destination-out';
        ctx.beginPath();
        torontoPolygon.forEach(([lng, lat], i) => {
          const pt = map.project([lng, lat]);
          if (i === 0) ctx.moveTo(pt.x, pt.y);
          else ctx.lineTo(pt.x, pt.y);
        });
        ctx.closePath();
        ctx.fill();
        ctx.globalCompositeOperation = 'source-over';
      };
      map.on('render', drawMask);

      // Toronto boundary: dashed + solid overlay (matches MapEditor exactly)
      map.addLayer({ id: 'toronto-boundary-dashed', type: 'line', source: 'toronto-boundary',
        paint: { 'line-color': '#1E3765', 'line-width': 3, 'line-dasharray': [1, 1] } });
      map.addLayer({ id: 'toronto-boundary-solid', type: 'line', source: 'toronto-boundary',
        paint: { 'line-color': '#1E3765', 'line-width': 1.5 } });

      // Transit lines — subway routes thicker
      map.addLayer({
        id: 'transit-lines-layer', type: 'line', source: 'transit-lines',
        paint: {
          'line-color': '#6FA8BB',
          'line-width': ['match', ['get', 'NAME'],
            ['Line 1: Yonge-University Subway', 'Line 2: Bloor-Danforth Subway', 'Line 4: Sheppard Subway'],
            1.25, 0.75],
        },
      }, 'water_polygons_labels_large');

      // Transit stations — subway stations larger
      map.addLayer({
        id: 'transit-stations-layer', type: 'circle', source: 'transit-stations',
        paint: {
          'circle-radius': ['match', ['get', 'NAME'],
            ['Line 1: Yonge-University Subway', 'Line 2: Bloor-Danforth Subway', 'Line 4: Sheppard Subway'],
            3, 2],
          'circle-color': '#6FA8BB',
          'circle-stroke-color': 'white',
          'circle-stroke-width': 1,
        },
      }, 'water_polygons_labels_large');

      // Priority park labels (High Park, islands, etc.)
      const priorityParks = ['High Park', 'Toronto Island Park', "Bluffer's Park",
        'Morningside Park', 'Rouge Park', 'Earl Bales Park'];
      map.addLayer({
        id: 'park-labels-priority', type: 'symbol', source: 'park-points', minzoom: 11,
        filter: ['in', ['get', 'name'], ['literal', priorityParks]],
        layout: { 'text-field': ['get', 'name'], 'text-font': ['Open Sans Italic'],
          'text-size': 11, 'text-offset': [0, 0.5], 'text-anchor': 'top', 'text-allow-overlap': false },
        paint: { 'text-color': '#5f8639', 'text-halo-color': 'white', 'text-halo-width': 1.5 },
      });

      // Priority transit station labels
      const priorityStations = ['Cedervale', 'Eglinton', 'Union', 'Kennedy', 'Kipling',
        'Finch West', 'Finch', 'Don Mills', 'Mount Dennis', 'St. George', 'Bloor-Yonge', 'Sheppard-Yonge'];
      map.addLayer({
        id: 'transit-station-labels', type: 'symbol', source: 'transit-stations', minzoom: 11.5,
        filter: ['all',
          ['in', ['get', 'LOCATION_N'], ['literal', priorityStations]],
          ['any', ['!=', ['get', 'LOCATION_N'], 'Eglinton'],
                  ['==', ['get', 'NAME'], 'Line 1: Yonge-University Subway']]],
        layout: { 'text-field': ['get', 'LOCATION_N'], 'text-font': ['Open Sans Bold'],
          'text-size': 11, 'text-offset': [0, 0.5], 'text-anchor': 'top', 'text-allow-overlap': false },
        paint: { 'text-color': '#5c7f8b', 'text-halo-color': 'white', 'text-halo-width': 1.5 },
      });
    });

    map.on('idle', () => { window.__mapReady = true; });
  </script>
</body>
</html>`;

  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Serve MapLibre from local node_modules — no network dependency for the script itself
  await page.route('**/maplibre-gl.js', route =>
    route.fulfill({ path: path.join(root, 'node_modules/maplibre-gl/dist/maplibre-gl.js') })
  );
  await page.route('**/maplibre-gl.css', route =>
    route.fulfill({ path: path.join(root, 'node_modules/maplibre-gl/dist/maplibre-gl.css') })
  );

  await page.setViewportSize({ width: WIDTH, height: MAP_HEIGHT });
  await page.setContent(html, { waitUntil: 'domcontentloaded' });

  // Wait until MapLibre signals idle (tiles loaded, mask drawn, fitBounds settled)
  await page.waitForFunction(() => (window as any).__mapReady === true, { timeout: 30000 });

  const screenshotBuffer = await page.screenshot();
  await browser.close();

  const outputPath = path.resolve('public/og-image.png');
  fs.mkdirSync('public', { recursive: true });

  // Stack the 1200×480 map screenshot + 150px navy bar = final 1200×630 PNG
  await sharp({
    create: { width: WIDTH, height: HEIGHT, channels: 4, background: { r: 255, g: 255, b: 255, alpha: 1 } },
  })
    .composite([
      { input: screenshotBuffer, top: 0, left: 0 },
      { input: Buffer.from(navyBarSvg), top: MAP_HEIGHT, left: 0 },
    ])
    .png()
    .toFile(outputPath);

  console.log(`✓ Written ${WIDTH}×${HEIGHT} image to ${outputPath}`);
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
