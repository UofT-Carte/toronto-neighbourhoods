import express from 'express';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { initializeApp, applicationDefault } from 'firebase-admin/app';
import { getFirestore } from 'firebase-admin/firestore';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const PORT = 4321;

const app = express();

const firebaseConfig = JSON.parse(
  readFileSync(join(ROOT, 'firebase-applet-config.json'), 'utf8'),
);

let _db = null;
function getDb() {
  if (!_db) {
    const adminApp = initializeApp({
      credential: applicationDefault(),
      projectId: firebaseConfig.projectId,
    });
    // Non-default database id — must be passed explicitly (matches src/firebase.ts).
    _db = getFirestore(adminApp, firebaseConfig.firestoreDatabaseId);
  }
  return _db;
}

app.get('/api/submissions', async (_req, res) => {
  try {
    const db = getDb();
    const snap = await db.collection('neighborhoods').get();
    const submissions = snap.docs.map((doc) => {
      const d = doc.data();
      const createdAt =
        d.createdAt && typeof d.createdAt.toDate === 'function'
          ? d.createdAt.toDate().toISOString()
          : null;
      return {
        id: doc.id,
        neighborhoodName: d.neighborhoodName ?? '',
        homeLocation: d.homeLocation ?? null,
        polygonPoints: d.polygonPoints ?? [],
        changesText: d.changesText ?? '',
        otherNamesText: d.otherNamesText ?? '',
        createdAt,
      };
    });
    // Newest first; nulls (missing createdAt) sort last.
    submissions.sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? ''));
    res.json(submissions);
  } catch (err) {
    console.error('Failed to read submissions:', err);
    res.status(500).json({
      error: String(err?.message ?? err),
      hint: 'Ensure you are authenticated: run `gcloud auth application-default login` with access to the Firebase project.',
    });
  }
});

// Serve the app's map style so the dashboard map matches the site.
app.get('/map-style.json', (_req, res) => {
  res.sendFile(join(ROOT, 'src', 'assets', 'map-style.json'), (err) => {
    if (err) res.status(500).send(String(err.message ?? err));
  });
});

// Serve the dashboard page.
app.get('/', (_req, res) => {
  res.sendFile(join(__dirname, 'index.html'), (err) => {
    if (err) res.status(500).send(String(err.message ?? err));
  });
});

app.listen(PORT, '127.0.0.1', () => {
  console.log(`\n  Submissions dashboard running at http://localhost:${PORT}\n`);
});
