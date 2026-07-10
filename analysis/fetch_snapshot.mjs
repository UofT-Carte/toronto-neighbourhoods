import { mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { initializeApp, applicationDefault } from 'firebase-admin/app';
import { getFirestore } from 'firebase-admin/firestore';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const DATA_DIR = join(__dirname, 'data');

const firebaseConfig = JSON.parse(
  readFileSync(join(ROOT, 'firebase-applet-config.json'), 'utf8'),
);

const adminApp = initializeApp({
  credential: applicationDefault(),
  projectId: firebaseConfig.projectId,
});
const db = getFirestore(adminApp, firebaseConfig.firestoreDatabaseId);

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
    otherNamesText: d.otherNamesText ?? '',
    changesText: d.changesText ?? '',
    createdAt,
  };
});

const stamp = new Date().toISOString().slice(0, 10);
mkdirSync(DATA_DIR, { recursive: true });
const outPath = join(DATA_DIR, `snapshot-${stamp}.json`);
writeFileSync(outPath, JSON.stringify(submissions, null, 2));
console.log(`Wrote ${submissions.length} submissions to ${outPath}`);
process.exit(0);
