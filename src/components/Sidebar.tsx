import { createPortal } from "react-dom";
import type React from "react";
import type { Dispatch, SetStateAction, FormEvent } from "react";
import { useState, useEffect, useRef } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Undo2, X, MapPin, Share2, Copy, Check } from "lucide-react";
import type { LatLngTuple } from "leaflet";
import { collection, addDoc, doc, updateDoc, getDoc, serverTimestamp } from "firebase/firestore";
import { db, handleFirestoreError, OperationType } from "../firebase";
import logoUofT          from '../assets/logos/logo-uoft.svg?url';
import logoSchoolCities  from '../assets/logos/logo-school-of-cities.svg?url';
import logoCarte         from '../assets/logos/logo-carte.svg?url';

interface NeighborhoodDoc {
  neighborhoodName: string;
  homeLocation: LatLngTuple;
  polygonPoints: Array<{ lat: number; lng: number }>;
  changesText: string;
  otherNamesText: string;
  createdAt?: ReturnType<typeof serverTimestamp>;
}

function Modal({ title, children, onClose, footer }: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  footer: React.ReactNode;
}) {
  return createPortal(
    <AnimatePresence>
      <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/50">
        <motion.div
          className="bg-white shadow-[0_8px_32px_rgba(30,55,101,0.2)] max-w-md w-full p-6 relative"
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
        >
          <button
            onClick={onClose}
            aria-label="Close"
            className="absolute top-4 right-4 text-uoft-teal bg-uoft-tint-light hover:bg-uoft-tint-bg p-1.5 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
          <h3 className="text-xl font-black text-uoft-blue mb-4 pr-8 leading-tight">{title}</h3>
          {children}
          <div className="mt-6 flex justify-end">{footer}</div>
        </motion.div>
      </div>
    </AnimatePresence>,
    document.body
  );
}

interface SidebarProps {
  step: 1 | 2 | 3;
  setStep: Dispatch<SetStateAction<1 | 2 | 3>>;
  homeLocation: LatLngTuple | null;
  setHomeLocation: Dispatch<SetStateAction<LatLngTuple | null>>;
  neighborhoodName: string;
  setNeighborhoodName: Dispatch<SetStateAction<string>>;
  polygonPoints: LatLngTuple[];
  setPolygonPoints: Dispatch<SetStateAction<LatLngTuple[]>>;
  isFinished: boolean;
  setIsFinished: Dispatch<SetStateAction<boolean>>;
  isAppSubmitted: boolean;
  setIsAppSubmitted: Dispatch<SetStateAction<boolean>>;
}

export default function Sidebar({
  step,
  setStep,
  homeLocation,
  setHomeLocation,
  neighborhoodName,
  setNeighborhoodName,
  polygonPoints,
  setPolygonPoints,
  isFinished,
  setIsFinished,
  isAppSubmitted,
  setIsAppSubmitted,
}: SidebarProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [changesText, setChangesText] = useState("");
  const [otherNamesText, setOtherNamesText] = useState("");
  const [isDataModalOpen, setIsDataModalOpen] = useState(false);
  const [isWelcomeModalOpen, setIsWelcomeModalOpen] = useState(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("hasSeenWelcomeModal") !== "true";
    }
    return true;
  });

  const [copied, setCopied] = useState(false);
  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const canNativeShare = typeof navigator !== 'undefined' && !!navigator.share;
  const canCopyToClipboard = typeof navigator !== 'undefined' && !!navigator.clipboard;

  const handleShare = async () => {
    const url = window.location.href;
    if (canNativeShare) {
      try {
        await navigator.share({
          title: 'Draw Your Toronto Neighbourhood',
          text: 'Help map Toronto by drawing your neighbourhood boundary',
          url,
        });
      } catch {
        // user cancelled or browser blocked — do nothing
      }
    } else if (canCopyToClipboard) {
      try {
        await navigator.clipboard.writeText(url);
        setCopied(true);
        if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
        copyTimeoutRef.current = setTimeout(() => setCopied(false), 2000);
      } catch {
        // clipboard write failed — do nothing
      }
    }
  };

  const handleCloseWelcomeModal = () => {
    setIsWelcomeModalOpen(false);
    localStorage.setItem("hasSeenWelcomeModal", "true");
  };
  
  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
    };
  }, []);

  useEffect(() => {
    const checkExistingSubmission = async () => {
      if (localStorage.getItem("hasSubmittedNeighborhood") === "true") {
        setIsAppSubmitted(true);
        setStep(3);

        const docId = localStorage.getItem("submittedNeighborhoodId");
        if (docId) {
          try {
            const snap = await getDoc(doc(db, "neighborhoods", docId));
            if (snap.exists()) {
              const data = snap.data();
              setNeighborhoodName(data.neighborhoodName || "");
              setHomeLocation(data.homeLocation as LatLngTuple || null);
              if (data.polygonPoints && Array.isArray(data.polygonPoints)) {
                setPolygonPoints((data.polygonPoints as Array<{ lat: number; lng: number }>).map(p => [p.lat, p.lng] as LatLngTuple));
                setIsFinished(true);
              }
              setChangesText(data.changesText || "");
              setOtherNamesText(data.otherNamesText || "");
            }
          } catch (e) {
            console.error("Failed to load existing submission", e);
          }
        }
      }
    };
    checkExistingSubmission();
  }, [setIsAppSubmitted, setStep, setNeighborhoodName, setHomeLocation, setPolygonPoints, setIsFinished]);

  const handleUndo = () => {
    setPolygonPoints((prev) => prev.slice(0, -1));
    setIsFinished(false);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!homeLocation) return;
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      if (import.meta.env.DEV) {
        console.log('[DEV] Skipping Firestore write. Payload:', {
          neighborhoodName: neighborhoodName.trim(),
          homeLocation,
          polygonPoints: polygonPoints.map(p => ({ lat: p[0], lng: p[1] })),
          changesText: changesText.trim(),
          otherNamesText: otherNamesText.trim(),
        });
        setIsAppSubmitted(true);
        return;
      }
      const pathForWrite = 'neighborhoods';
      let docRefId = localStorage.getItem("submittedNeighborhoodId");
      
      const payload: Omit<NeighborhoodDoc, 'createdAt'> = {
        neighborhoodName: neighborhoodName.trim(),
        homeLocation,
        polygonPoints: polygonPoints.map(p => ({ lat: p[0], lng: p[1] })),
        changesText: changesText.trim(),
        otherNamesText: otherNamesText.trim(),
      };

      try {
        if (docRefId) {
          await updateDoc(doc(db, pathForWrite, docRefId), payload);
        } else {
          payload.createdAt = serverTimestamp();
          const newDoc = await addDoc(collection(db, pathForWrite), payload);
          docRefId = newDoc.id;
        }
      } catch (err) {
        handleFirestoreError(err, OperationType.WRITE, pathForWrite);
      }
      setIsAppSubmitted(true);
      localStorage.setItem("hasSubmittedNeighborhood", "true");
      if (docRefId) localStorage.setItem("submittedNeighborhoodId", docRefId);
    } catch (err) {
      console.error(err);
      setSubmitError("Failed to submit. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="w-full h-[45dvh] md:h-[100dvh] md:w-[24rem] bg-white shrink-0 overflow-y-auto border-t md:border-t-0 md:border-r border-uoft-border flex flex-col font-sans relative z-10 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.1)] md:shadow-[0_8px_32px_rgba(30,55,101,0.18)]">

    {/* Dark UofT Blue header */}
    <div className="bg-uoft-blue relative overflow-hidden shrink-0">
      {/* Subtle teal gradient overlay for depth */}
      <div className="absolute inset-0 pointer-events-none" style={{ background: 'linear-gradient(135deg, rgba(0,120,148,0.25) 0%, transparent 60%)' }} />
      <div className="relative z-10 px-5 pt-5 pb-4 md:px-6 md:pt-6 md:pb-5">
        <h1 className="text-2xl md:text-[1.65rem] font-black text-white leading-tight tracking-tight">
          Toronto<br />Neighbourhoods
        </h1>
      </div>
      {/* Teal gradient rule */}
      <div className="h-1" style={{ background: 'linear-gradient(90deg, #007894 0%, #6FC7EA 100%)' }} />
    </div>

    {/* Progress tabs */}
    <div className="flex bg-uoft-tint-bg border-b border-uoft-border shrink-0">
      {([
        { n: 1, label: 'Name' },
        { n: 2, label: 'Draw' },
        { n: 3, label: 'Submit' },
      ] as const).map(({ n, label }) => {
        const isDone   = step > n || isAppSubmitted;
        const isActive = step === n && !isAppSubmitted;
        return (
          <div
            key={n}
            className={[
              'flex-1 text-center py-2 text-[11px] font-bold border-r border-uoft-border last:border-r-0',
              isDone   ? 'text-uoft-teal bg-uoft-tint-light' : '',
              isActive ? 'text-uoft-blue bg-white border-b-2 border-b-uoft-blue -mb-px' : '',
              !isDone && !isActive ? 'text-uoft-label' : '',
            ].join(' ')}
          >
            <span className="block text-sm font-black leading-none mb-0.5">
              {isDone ? '✓' : n}
            </span>
            {label}
          </div>
        );
      })}
    </div>

    <div className="flex-1 flex flex-col overflow-y-auto">

      {/* ── Non-submitted flow ── */}
      {!isAppSubmitted && (
        <>
          {/* Step 1 — done (collapsed) */}
          {step > 1 && neighborhoodName && (
            <div className="bg-uoft-tint-step border-b border-uoft-border px-5 py-3 flex items-center gap-3 border-l-4 border-l-uoft-sky">
              <div className="w-5 h-5 bg-uoft-teal rounded-full flex items-center justify-center text-white text-[10px] font-black shrink-0">✓</div>
              <div className="flex-1 min-w-0">
                <div className="text-[11px] font-bold text-uoft-teal">Step 1 · Neighbourhood name</div>
                <div className="text-sm font-bold text-uoft-blue truncate">{neighborhoodName}</div>
              </div>
              <button onClick={() => setStep(1)} className="text-[11px] font-bold text-uoft-teal underline shrink-0">Edit</button>
            </div>
          )}

          {/* Step 1 — active */}
          {step === 1 && (
            <div className="border-l-4 border-l-uoft-blue px-5 py-5 md:px-6">
              <div className="text-[12px] font-bold text-uoft-teal mb-1.5">Step 1 of 3</div>
              <h2 className="text-[17px] font-black text-uoft-blue leading-snug mb-3">What do you call the neighbourhood where you live?</h2>
              <form onSubmit={(e) => { e.preventDefault(); if (neighborhoodName.trim()) setStep(2); }} className="flex flex-col gap-3">
                <input
                  type="text"
                  required
                  name="neighborhood_name_input"
                  value={neighborhoodName}
                  onChange={(e) => setNeighborhoodName(e.target.value)}
                  maxLength={150}
                  placeholder="e.g. The Annex, Leslieville…"
                  className="border-2 border-uoft-border px-3 py-2.5 text-[15px] text-uoft-blue bg-[#fafdff] focus:outline-none focus:border-uoft-blue w-full"
                  autoComplete="off"
                  data-1p-ignore="true"
                />
                <button
                  type="submit"
                  disabled={!neighborhoodName.trim()}
                  className="bg-uoft-blue text-white text-[13px] font-bold py-2.5 px-5 hover:bg-[#162d55] transition-colors w-max disabled:opacity-50"
                >
                  Next
                </button>
              </form>
            </div>
          )}

          {/* Step 2 — done (collapsed) */}
          {step > 2 && isFinished && (
            <div className="bg-uoft-tint-step border-b border-uoft-border px-5 py-3 flex items-center gap-3 border-l-4 border-l-uoft-sky">
              <div className="w-5 h-5 bg-uoft-teal rounded-full flex items-center justify-center text-white text-[10px] font-black shrink-0">✓</div>
              <div className="flex-1 min-w-0">
                <div className="text-[11px] font-bold text-uoft-teal">Step 2 · Boundary drawn</div>
                <div className="text-sm font-bold text-uoft-blue">{polygonPoints.length} points</div>
              </div>
              <button
                onClick={() => { setStep(2); setPolygonPoints([]); setIsFinished(false); setHomeLocation(null); }}
                className="text-[11px] font-bold text-uoft-teal underline shrink-0"
              >
                Redraw
              </button>
            </div>
          )}

          {/* Step 2 — active */}
          {step === 2 && (
            <div className="border-l-4 border-l-uoft-blue px-5 py-5 md:px-6">
              <div className="text-[12px] font-bold text-uoft-teal mb-1.5">Step 2 of 3</div>
              <h2 className="text-[17px] font-black text-uoft-blue leading-snug mb-2">Trace your neighbourhood</h2>
              <p className="text-[14px] text-uoft-body leading-relaxed">Click to place points around the boundary. Connect back to the start to close the shape.</p>
              {polygonPoints.length > 0 && (
                <button
                  onClick={handleUndo}
                  className="flex items-center gap-1.5 text-[13px] font-bold text-uoft-teal border-b-2 border-uoft-teal mt-4 pb-0.5 hover:text-uoft-blue hover:border-uoft-blue transition-colors"
                >
                  <Undo2 className="w-3.5 h-3.5" /> Undo last point
                </button>
              )}
            </div>
          )}

          {/* Step 3 — active (form) */}
          {step === 3 && (
            <div className="border-l-4 border-l-uoft-blue px-5 py-5 md:px-6 flex flex-col gap-5">
              <div>
                <div className="text-[12px] font-bold text-uoft-teal mb-1.5">Step 3 of 3</div>
                <h2 className="text-[17px] font-black text-uoft-blue leading-snug">Tell us more</h2>
              </div>
              <form id="submit-form" className="flex flex-col gap-5" onSubmit={handleSubmit}>
                <div className="flex flex-col gap-1.5">
                  <label className="text-[14px] font-bold text-uoft-blue leading-snug">
                    How would you say these boundaries changed over the years?{' '}
                    <span className="font-normal text-uoft-muted">(optional)</span>
                  </label>
                  <p className="text-[12px] text-uoft-muted">For example, has the neighbourhood stretched in one direction?</p>
                  <textarea
                    name="changes_text"
                    rows={3}
                    maxLength={5000}
                    className="border-2 border-uoft-border p-3 text-[14px] text-uoft-blue focus:outline-none focus:border-uoft-blue resize-y bg-white"
                    value={changesText}
                    onChange={(e) => setChangesText(e.target.value)}
                    autoComplete="off"
                    data-1p-ignore="true"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-[14px] font-bold text-uoft-blue leading-snug">
                    Does this neighbourhood go by any other names?{' '}
                    <span className="font-normal text-uoft-muted">(optional)</span>
                  </label>
                  <p className="text-[12px] text-uoft-muted">For example, parts of The Danforth are also called Greektown.</p>
                  <textarea
                    name="other_names_text"
                    rows={3}
                    maxLength={1000}
                    className="border-2 border-uoft-border p-3 text-[14px] text-uoft-blue focus:outline-none focus:border-uoft-blue resize-y bg-white"
                    value={otherNamesText}
                    onChange={(e) => setOtherNamesText(e.target.value)}
                    autoComplete="off"
                    data-1p-ignore="true"
                  />
                </div>
                {submitError && <div className="text-red-600 text-sm">{submitError}</div>}
              </form>
            </div>
          )}

        </>
      )}

      {/* ── Already-submitted state ── */}
      {isAppSubmitted && (
        <div className="bg-uoft-tint-light border border-uoft-border text-center p-6 m-4">
          <div className="w-12 h-12 bg-uoft-tint-light border-2 border-uoft-teal text-uoft-teal flex items-center justify-center mx-auto mb-4">
            <MapPin className="w-6 h-6" />
          </div>
          <h4 className="font-black text-uoft-blue text-lg mb-2">Submission Received</h4>
          <p className="text-uoft-body text-sm mb-4">You have already submitted a neighbourhood map. Thank you!</p>
          <button
            onClick={() => setIsAppSubmitted(false)}
            className="text-sm font-bold text-uoft-teal border-2 border-uoft-teal py-2.5 px-4 hover:bg-uoft-tint-light transition-colors w-full"
          >
            Edit my submission
          </button>
          {(canNativeShare || canCopyToClipboard) && (
            <div className="border-t border-uoft-border pt-4 mt-4">
              <p className="text-uoft-body text-sm mb-3">Help us map the whole city — share with your neighbours.</p>
              <button
                onClick={handleShare}
                aria-label="Share this site with others"
                className="flex items-center justify-center gap-2 text-sm font-bold text-uoft-teal border-2 border-uoft-teal py-2.5 px-4 hover:bg-uoft-tint-light transition-colors w-full"
              >
                {copied ? (
                  <><Check className="w-4 h-4" /> Copied!</>
                ) : canNativeShare ? (
                  <><Share2 className="w-4 h-4" /> Share with others</>
                ) : (
                  <><Copy className="w-4 h-4" /> Copy link</>
                )}
              </button>
            </div>
          )}
        </div>
      )}

    </div>
    {/* Submit bar — step 3 only */}
    {step === 3 && !isAppSubmitted && (
      <div className="bg-uoft-blue px-5 py-4 flex items-center justify-between gap-4 shrink-0">
        <p className="text-uoft-sky text-[11px] leading-snug max-w-[140px]">Your map will be added to our dataset</p>
        <button
          type="submit"
          form="submit-form"
          disabled={isSubmitting}
          className="text-white text-[13px] font-bold border-2 border-white py-2.5 px-5 hover:bg-[#162d55] transition-colors disabled:opacity-50 shrink-0"
        >
          {isSubmitting ? 'Submitting…' : 'Submit my map →'}
        </button>
      </div>
    )}

    {/* Logo strip */}
    <div className="bg-white border-t border-uoft-border px-4 py-3 flex items-center justify-between gap-2 shrink-0" style={{ minHeight: '56px' }}>
      <div className="flex-1 flex items-center justify-center">
        <a href="https://utoronto.ca" target="_blank" rel="noopener noreferrer" className="flex items-center justify-center w-full">
          <img src={logoUofT} alt="University of Toronto" style={{ maxHeight: '28px', width: 'auto', maxWidth: '100%' }} />
        </a>
      </div>
      <div className="w-px h-8 bg-uoft-border shrink-0" />
      <div className="flex-1 flex items-center justify-center">
        <a href="https://schoolofcities.utoronto.ca" target="_blank" rel="noopener noreferrer" className="flex items-center justify-center w-full">
          <img src={logoSchoolCities} alt="School of Cities" style={{ maxHeight: '28px', width: 'auto', maxWidth: '100%' }} />
        </a>
      </div>
      <div className="w-px h-8 bg-uoft-border shrink-0" />
      <div className="flex-1 flex items-center justify-center">
        <a href="https://carte.utoronto.ca" target="_blank" rel="noopener noreferrer" className="flex items-center justify-center w-full">
          <img src={logoCarte} alt="Carte" style={{ maxHeight: '44px', width: 'auto', maxWidth: '100%' }} />
        </a>
      </div>
    </div>

    {/* Text footer */}
    <div className="px-5 py-2.5 text-[11px] text-uoft-muted bg-uoft-tint-bg border-t border-uoft-border shrink-0 flex justify-between gap-3 leading-relaxed">
      <p>Inspired by the NYT's <a href="https://www.nytimes.com/interactive/2022/12/02/upshot/draw-your-nyc-neighborhood.html" target="_blank" rel="noopener noreferrer" className="text-uoft-teal font-bold underline hover:text-uoft-blue">"Draw Your NYC Neighborhood"</a></p>
      <button
        onClick={() => setIsDataModalOpen(true)}
        className="text-uoft-teal font-bold underline hover:text-uoft-blue shrink-0"
      >
        Data info
      </button>
    </div>

      {isDataModalOpen && (
        <Modal
          title="What data we store"
          onClose={() => setIsDataModalOpen(false)}
          footer={
            <button
              onClick={() => setIsDataModalOpen(false)}
              className="px-5 py-2.5 bg-uoft-blue text-white font-bold hover:bg-[#162d55] transition-colors"
            >
              Got it
            </button>
          }
        >
          <div className="space-y-4 text-sm text-uoft-body leading-relaxed">
            <p>When you submit your map, we store the following data in our database securely:</p>
            <ul className="list-disc pl-5 space-y-2">
              <li><strong className="text-uoft-blue">Your neighbourhood's name</strong> (including alternate names you might suggest).</li>
              <li><strong className="text-uoft-blue">The centre of your drawn boundary</strong> (a single latitude/longitude coordinate calculated from the shape you drew).</li>
              <li><strong className="text-uoft-blue">The boundary polygon</strong> (the shape of the neighbourhood you drew).</li>
              <li><strong className="text-uoft-blue">Optional feedback</strong> on how the neighbourhood is changing.</li>
              <li><strong className="text-uoft-blue">A timestamp</strong> of when the submission was made.</li>
            </ul>
            <p>We <strong>do not</strong> collect your name, email address, IP address, or any personally identifiable information (PII). No authentication is required to participate.</p>
            <div className="pt-2 border-t border-uoft-border">
              <p>A project by <a href="https://carte.utoronto.ca/" target="_blank" rel="noopener noreferrer" className="text-uoft-teal font-bold underline hover:text-uoft-blue">Carte</a>, UofT Engineering's applied AI hub, and the <a href="https://schoolofcities.utoronto.ca/" target="_blank" rel="noopener noreferrer" className="text-uoft-teal font-bold underline hover:text-uoft-blue">School of Cities</a>, a multidisciplinary hub for urban research, education, and engagement at the University of Toronto.</p>
            </div>
          </div>
        </Modal>
      )}

      {isWelcomeModalOpen && (
        <Modal
          title="Draw Your Toronto Neighbourhood"
          onClose={handleCloseWelcomeModal}
          footer={
            <button
              onClick={handleCloseWelcomeModal}
              className="px-6 py-2.5 bg-uoft-blue text-white font-bold hover:bg-[#162d55] transition-colors"
            >
              Let's go
            </button>
          }
        >
          <div className="space-y-4 text-[15px] text-uoft-body leading-relaxed">
            <p>Official city boundaries don't always match how residents actually experience their neighbourhoods. This research project, led by Carte and the School of Cities at the University of Toronto, is building a new map of Toronto based on how the people who live here define it.</p>
            <p>Help us by drawing where you think your neighbourhood begins and ends.</p>
            <div className="pt-2 border-t border-uoft-border text-sm">
              <p>A project by <a href="https://carte.utoronto.ca/" target="_blank" rel="noopener noreferrer" className="text-uoft-teal font-bold underline hover:text-uoft-blue">Carte</a>, UofT Engineering's applied AI hub, and the <a href="https://schoolofcities.utoronto.ca/" target="_blank" rel="noopener noreferrer" className="text-uoft-teal font-bold underline hover:text-uoft-blue">School of Cities</a>, a multidisciplinary hub for urban research, education, and engagement at the University of Toronto.</p>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
