from collections import defaultdict

from shapely import STRtree

from geometry import iou


def contested_pairs(records, iou_threshold: float):
    polys = [r["poly"] for r in records]
    if len(polys) < 2:
        return []
    tree = STRtree(polys)

    agg = defaultdict(lambda: {"count": 0, "iou_sum": 0.0})
    for i, r in enumerate(records):
        for j in tree.query(polys[i]):
            if j <= i:
                continue
            other = records[j]
            if other["cluster_id"] == r["cluster_id"]:
                continue
            score = iou(polys[i], polys[j])
            if score < iou_threshold:
                continue
            key = tuple(sorted((r["label"], other["label"])))
            agg[key]["count"] += 1
            agg[key]["iou_sum"] += score

    rows = [
        {
            "label_a": k[0],
            "label_b": k[1],
            "overlap_count": v["count"],
            "mean_iou": v["iou_sum"] / v["count"],
        }
        for k, v in agg.items()
    ]
    rows.sort(key=lambda x: (x["overlap_count"], x["mean_iou"]), reverse=True)
    return rows
