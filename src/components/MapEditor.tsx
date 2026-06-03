import type { Dispatch, SetStateAction } from "react";
import { useState, useMemo, useRef, useEffect, useCallback } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import pointInPolygon from "point-in-polygon";

import torontoGeoJson from "../assets/toronto-data/toronto.json";
import mapStyle from "../assets/map-style.json";
import transitLines from "../assets/toronto-data/current-lines.geo.json";
import transitStations from "../assets/toronto-data/current-stations.geo.json";
import parkPoints from "../assets/toronto-data/park-points.geo.json";

type LatLngTuple = [number, number];

const TORONTO_POLYGON_LNG_LAT = torontoGeoJson.coordinates[0] as [number, number][];

const TORONTO_BOUNDS: [[number, number], [number, number]] = [
  [-79.9, 43.4],
  [-78.8, 44.0]
];

const TORONTO_FIT_BOUNDS: [[number, number], [number, number]] = TORONTO_POLYGON_LNG_LAT.reduce(
  ([[minLng, minLat], [maxLng, maxLat]], [lng, lat]) => [
    [Math.min(minLng, lng), Math.min(minLat, lat)],
    [Math.max(maxLng, lng), Math.max(maxLat, lat)],
  ],
  [[Infinity, Infinity], [-Infinity, -Infinity]]
);


function isPointInToronto(lat: number, lng: number): boolean {
  return pointInPolygon([lng, lat], TORONTO_POLYGON_LNG_LAT);
}


const torontoBoundaryLine = {
  type: "Feature" as const,
  geometry: {
    type: "LineString" as const,
    coordinates: TORONTO_POLYGON_LNG_LAT,
  },
};

const emptyGeoJSON = {
  type: "FeatureCollection" as const,
  features: [],
};

function createLineFeature(points: LatLngTuple[]) {
  return {
    type: "Feature" as const,
    geometry: {
      type: "LineString" as const,
      coordinates: points.map(([lat, lng]) => [lng, lat]),
    },
  };
}

function createPolygonFeature(points: LatLngTuple[]) {
  const ring = points.map(([lat, lng]) => [lng, lat] as [number, number]);
  // GeoJSON exterior rings must be counter-clockwise and explicitly closed
  const closed = [...ring, ring[0]];
  const area = closed.slice(0, -1).reduce((sum, [x, y], i) => {
    const [nx, ny] = closed[i + 1];
    return sum + (x * ny - nx * y);
  }, 0);
  const ccw = area < 0 ? closed : [...closed].reverse();
  return {
    type: "Feature" as const,
    properties: {},
    geometry: {
      type: "Polygon" as const,
      coordinates: [ccw],
    },
  };
}

function createPointFeature(lat: number, lng: number) {
  return {
    type: "FeatureCollection" as const,
    features: [{
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [lng, lat] },
      properties: {},
    }],
  };
}

function createPointCollection(points: LatLngTuple[]) {
  return {
    type: "FeatureCollection" as const,
    features: points.map((point, index) => ({
      type: "Feature" as const,
      geometry: {
        type: "Point" as const,
        coordinates: [point[1], point[0]],
      },
      properties: {
        isFirst: index === 0,
      },
    })),
  };
}

interface MapEditorProps {
  step: 1 | 2 | 3;
  setStep: Dispatch<SetStateAction<1 | 2 | 3>>;
  homeLocation: LatLngTuple | null;
  setHomeLocation: Dispatch<SetStateAction<LatLngTuple | null>>;
  polygonPoints: LatLngTuple[];
  setPolygonPoints: Dispatch<SetStateAction<LatLngTuple[]>>;
  isFinished: boolean;
  setIsFinished: Dispatch<SetStateAction<boolean>>;
  isAppSubmitted: boolean;
}

export default function MapEditor({
  step,
  setStep,
  homeLocation,
  setHomeLocation,
  polygonPoints,
  setPolygonPoints,
  isFinished,
  setIsFinished,
  isAppSubmitted,
}: MapEditorProps) {
  const [mousePos, setMousePos] = useState<LatLngTuple | null>(null);
  const [isMapReady, setIsMapReady] = useState(false);
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  const closePolygon = useCallback(() => {
    if (polygonPoints.length > 0) {
      const centroid: LatLngTuple = [
        polygonPoints.reduce((s, p) => s + p[0], 0) / polygonPoints.length,
        polygonPoints.reduce((s, p) => s + p[1], 0) / polygonPoints.length,
      ];
      setHomeLocation(centroid);
    }
    setIsFinished(true);
    setMousePos(null);
    setStep(3);
  }, [setIsFinished, setStep, polygonPoints, setHomeLocation]);

  const ghostLineParams = useMemo(() => {
    if (isAppSubmitted || step !== 2 || isFinished || polygonPoints.length === 0 || !mousePos) return null;
    const lastPoint = polygonPoints[polygonPoints.length - 1];
    return [lastPoint, mousePos] as [LatLngTuple, LatLngTuple];
  }, [step, isFinished, polygonPoints, mousePos, isAppSubmitted]);

  useEffect(() => {
    if (!mapContainerRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: mapStyle as maplibregl.StyleSpecification,
      center: [-79.3832, 43.6532],
      zoom: 11,
      bearing: 0,
      scrollZoom: true,
      minZoom: 8,
      maxZoom: 16,
      pitch: 0,
      pitchWithRotate: false,
      dragRotate: false,
      touchPitch: false,
      projection: "mercator",
      attributionControl: false,
      maxBounds: TORONTO_BOUNDS,
    });

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");

    mapRef.current = map;

    const maskCanvas = document.createElement("canvas");

    const parkLabelLayout: maplibregl.SymbolLayerSpecification["layout"] = {
      "text-field": ["get", "name"],
      "text-font": ["Open Sans Italic"],
      "text-size": 11,
      "text-offset": [0, 0.5],
      "text-anchor": "top",
      "text-allow-overlap": false,
    };
    const parkLabelPaint = {
      "text-color": "#5f8639",
      "text-halo-color": "white",
      "text-halo-width": 1.5,
    };
    const stationLabelPaint = {
      "text-color": "#5c7f8b",
      "text-halo-color": "white",
      "text-halo-width": 1.5,
    };

    const onLoad = () => {
      const w = mapContainerRef.current!.offsetWidth;
      const h = mapContainerRef.current!.offsetHeight;
      const padding = Math.min(w, h) * 0.04;
      map.fitBounds(TORONTO_FIT_BOUNDS, { padding, bearing: 0, animate: false });
      map.easeTo({ bearing: -17, duration: 800, easing: (t) => t * (2 - t) });
      maskCanvas.style.cssText = "position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:1";
      mapContainerRef.current!.appendChild(maskCanvas);

      const drawMask = () => {
        const w = mapContainerRef.current!.offsetWidth;
        const h = mapContainerRef.current!.offsetHeight;
        maskCanvas.width = w;
        maskCanvas.height = h;
        const ctx = maskCanvas.getContext("2d")!;
        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = "rgba(255,255,255,0.75)";
        ctx.fillRect(0, 0, w, h);
        ctx.globalCompositeOperation = "destination-out";
        ctx.beginPath();
        TORONTO_POLYGON_LNG_LAT.forEach(([lng, lat], i) => {
          const pt = map.project([lng, lat]);
          if (i === 0) ctx.moveTo(pt.x, pt.y);
          else ctx.lineTo(pt.x, pt.y);
        });
        ctx.closePath();
        ctx.fill();
        ctx.globalCompositeOperation = "source-over";
      };

      map.on("render", drawMask);

      map.addSource("transit-lines", {
        type: "geojson",
        data: transitLines as GeoJSON.FeatureCollection,
      });
      map.addLayer(
        {
          id: "transit-lines",
          type: "line",
          source: "transit-lines",
          paint: {
            "line-color": "#6FA8BB",
            "line-width": [
              "match",
              ["get", "NAME"],
              ["Line 1: Yonge-University Subway", "Line 2: Bloor-Danforth Subway", "Line 4: Sheppard Subway"],
              1.25,
              0.75,
            ],
          },
        },
        "water_polygons_labels_large"
      );

      map.addSource("transit-stations", {
        type: "geojson",
        data: transitStations as GeoJSON.FeatureCollection,
      });
      map.addLayer(
        {
          id: "transit-stations",
          type: "circle",
          source: "transit-stations",
          paint: {
            "circle-radius": [
              "match",
              ["get", "NAME"],
              ["Line 1: Yonge-University Subway", "Line 2: Bloor-Danforth Subway", "Line 4: Sheppard Subway"],
              3,
              2,
            ],
            "circle-color": "#6FA8BB",
            "circle-stroke-color": "white",
            "circle-stroke-width": 1,
          },
        },
        "water_polygons_labels_large"
      );


      map.addSource("park-points", {
        type: "geojson",
        data: parkPoints as GeoJSON.FeatureCollection,
      });
      const priorityParks = [
        "High Park", "Toronto Island Park", "Bluffer's Park",
        "Morningside Park", "Rouge Park", "Earl Bales Park"
      ];
      map.addLayer({
        id: "park-labels-priority",
        type: "symbol",
        source: "park-points",
        minzoom: 11,
        filter: ["in", ["get", "name"], ["literal", priorityParks]],
        layout: parkLabelLayout,
        paint: parkLabelPaint,
      });
      map.addLayer({
        id: "park-labels",
        type: "symbol",
        source: "park-points",
        minzoom: 14,
        filter: ["!", ["in", ["get", "name"], ["literal", priorityParks]]],
        layout: parkLabelLayout,
        paint: parkLabelPaint,
      });


      const priorityStations = [
        "Cedervale", "Eglinton", "Union", "Kennedy", "Kipling",
        "Finch West", "Finch", "Don Mills", "Mount Dennis",
        "St. George", "Bloor-Yonge", "Sheppard-Yonge",
      ];
      map.addLayer({
        id: "transit-station-labels-priority",
        type: "symbol",
        source: "transit-stations",
        minzoom: 11.5,
        filter: [
          "all",
          ["in", ["get", "LOCATION_N"], ["literal", priorityStations]],
          ["any",
            ["!=", ["get", "LOCATION_N"], "Eglinton"],
            ["==", ["get", "NAME"], "Line 1: Yonge-University Subway"],
          ],
        ],
        layout: {
          "text-field": ["get", "LOCATION_N"],
          "text-font": ["Open Sans Bold"],
          "text-size": 11,
          "text-offset": [0, 0.5],
          "text-anchor": "top",
          "text-allow-overlap": false,
          "symbol-sort-key": ["match", ["get", "LOCATION_N"], "Bloor-Yonge", 0, "St. George", 1, 2],
        },
        paint: stationLabelPaint,
      });
      map.addLayer({
        id: "transit-station-labels",
        type: "symbol",
        source: "transit-stations",
        minzoom: 12.5,
        filter: ["!", ["in", ["get", "LOCATION_N"], ["literal", priorityStations]]],
        layout: {
          "text-field": ["get", "LOCATION_N"],
          "text-font": ["Open Sans Bold"],
          "text-size": 11,
          "text-offset": [0, 0.5],
          "text-anchor": "top",
          "text-allow-overlap": false,
          "symbol-sort-key": -1,
        },
        paint: stationLabelPaint,
      });

      

      map.addSource("toronto-boundary-line", {
        type: "geojson",
        data: torontoBoundaryLine,
      });
      map.addLayer({
        id: "toronto-boundary-line",
        type: "line",
        source: "toronto-boundary-line",
        paint: {
          "line-color": "#1E3765",
          "line-width": 3,
          "line-dasharray": [1, 1],
        },
      });
      map.addLayer({
        id: "toronto-boundary-line-solid",
        type: "line",
        source: "toronto-boundary-line",
        paint: {
          "line-color": "#1E3765",
          "line-width": 1.5,
        },
      });

      map.addSource("polygon-line", {
        type: "geojson",
        data: emptyGeoJSON,
      });
      map.addLayer({
        id: "polygon-line",
        type: "line",
        source: "polygon-line",
        paint: {
          "line-color": "#1E3765",
          "line-width": 5,
          "line-dasharray": [2, 1],
        },
      });

      map.addSource("ghost-line", {
        type: "geojson",
        data: emptyGeoJSON,
      });
      map.addLayer({
        id: "ghost-line",
        type: "line",
        source: "ghost-line",
        paint: {
          "line-color": "#1E3765",
          "line-width": 3,
          "line-dasharray": [2, 1],
          "line-opacity": 0.5,
        },
      });

      map.addSource("polygon-fill", {
        type: "geojson",
        data: emptyGeoJSON,
        buffer: 512,
        tolerance: 0,
      });
      map.addLayer({
        id: "polygon-fill",
        type: "fill",
        source: "polygon-fill",
        paint: {
          "fill-color": "#1E3765",
          "fill-opacity": 0.5,
          "fill-antialias": true,
        },
      });
      map.addLayer({
        id: "polygon-fill-outline",
        type: "line",
        source: "polygon-fill",
        layout: {
          "line-join": "round",
          "line-cap": "round",
        },
        paint: {
          "line-color": "#F1C500",
          "line-width": 2,
        },
      });

      map.addSource("draw-points", {
        type: "geojson",
        data: emptyGeoJSON,
      });
      map.addLayer({
        id: "draw-points",
        type: "circle",
        source: "draw-points",
        paint: {
          "circle-radius": [
            "case",
            ["==", ["get", "isFirst"], true],
            8,
            4,
          ],
          "circle-color": "#1E3765",
          "circle-stroke-color": "white",
          "circle-stroke-width": 2,
        },
      });

      map.addSource("home-point", {
        type: "geojson",
        data: emptyGeoJSON,
      });
      map.addLayer({
        id: "home-point",
        type: "circle",
        source: "home-point",
        paint: {
          "circle-radius": 9,
          "circle-color": "#1E3765",
          "circle-stroke-color": "#F1C500",
          "circle-stroke-width": 2,
        },
      });

      setIsMapReady(true);
    };

    map.on("load", onLoad);

    return () => {
      map.off("load", onLoad);
      map.remove();
      maskCanvas.remove();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) return;

    const handleMouseMove = (e: maplibregl.MapMouseEvent) => {
      if (isAppSubmitted) return;
      if (step !== 2 || isFinished || polygonPoints.length === 0) return;
      if (isPointInToronto(e.lngLat.lat, e.lngLat.lng)) {
        setMousePos([e.lngLat.lat, e.lngLat.lng]);
      }
    };

    const handleClick = (e: maplibregl.MapMouseEvent) => {
      if (isAppSubmitted) return;
      if (!isPointInToronto(e.lngLat.lat, e.lngLat.lng)) return;

      if (step !== 2 || isFinished) return;

      if (polygonPoints.length > 2) {
        const firstPoint = polygonPoints[0];
        const firstPixel = map.project({ lng: firstPoint[1], lat: firstPoint[0] });
        const distance = Math.hypot(firstPixel.x - e.point.x, firstPixel.y - e.point.y);

        if (distance < 20) {
          closePolygon();
          return;
        }
      }

      if (polygonPoints.length >= 49) {
        alert("Maximum points reached for polygon.");
        closePolygon();
        return;
      }

      setPolygonPoints((prev) => [...prev, [e.lngLat.lat, e.lngLat.lng]]);
    };

    map.on("mousemove", handleMouseMove);
    map.on("click", handleClick);

    return () => {
      map.off("mousemove", handleMouseMove);
      map.off("click", handleClick);
    };
  }, [isMapReady, step, isFinished, polygonPoints, isAppSubmitted, setHomeLocation, setStep, setPolygonPoints, closePolygon]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) return;

    const polygonLineSource = map.getSource("polygon-line") as maplibregl.GeoJSONSource | null;
    const ghostLineSource = map.getSource("ghost-line") as maplibregl.GeoJSONSource | null;
    const polygonFillSource = map.getSource("polygon-fill") as maplibregl.GeoJSONSource | null;
    const drawPointsSource = map.getSource("draw-points") as maplibregl.GeoJSONSource | null;
    const homePointSource = map.getSource("home-point") as maplibregl.GeoJSONSource | null;

    polygonLineSource?.setData(
      polygonPoints.length > 0 && !isFinished ? createLineFeature(polygonPoints) : emptyGeoJSON
    );

    ghostLineSource?.setData(
      ghostLineParams ? createLineFeature(ghostLineParams) : emptyGeoJSON
    );

    polygonFillSource?.setData(
      isFinished && polygonPoints.length > 2 ? createPolygonFeature(polygonPoints) : emptyGeoJSON
    );

    drawPointsSource?.setData(
      step === 2 && polygonPoints.length > 0 ? createPointCollection(polygonPoints) : emptyGeoJSON
    );

    homePointSource?.setData(
      homeLocation ? createPointFeature(homeLocation[0], homeLocation[1]) : emptyGeoJSON
    );
  }, [isMapReady, polygonPoints, ghostLineParams, isFinished, step, homeLocation]);

  const cursorClass = !isAppSubmitted && step === 2 && !isFinished
    ? "cursor-crosshair"
    : "cursor-default";

  return (
    <div className={`w-full h-full relative ${cursorClass}`}>
      <div ref={mapContainerRef} className="w-full h-full" />
    </div>
  );
}
