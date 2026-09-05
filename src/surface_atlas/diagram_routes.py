"""Small deterministic orthogonal router for the report's fixed diagrams."""
from __future__ import annotations

import heapq


def route_between(start, end, obstacles, width, height):
    """Find a rectilinear route that never crosses a component's bounds."""
    xs = sorted({8, width - 8, start[0], end[0], *(v for r in obstacles for v in (r[0] - 12, r[2] + 12))})
    ys = sorted({8, height - 8, start[1], end[1], *(v for r in obstacles for v in (r[1] - 12, r[3] + 12))})
    xs = [x for x in xs if 0 <= x <= width]
    ys = [y for y in ys if 0 <= y <= height]

    def clear(a, b):
        for left, top, right, bottom in obstacles:
            if a[0] == b[0] and left < a[0] < right and max(a[1], b[1]) > top and min(a[1], b[1]) < bottom:
                return False
            if a[1] == b[1] and top < a[1] < bottom and max(a[0], b[0]) > left and min(a[0], b[0]) < right:
                return False
        return True

    source = (xs.index(start[0]), ys.index(start[1]))
    destination = (xs.index(end[0]), ys.index(end[1]))
    queue = [(0, source, -1, [start])]
    best = {}
    while queue:
        cost, (i, j), direction, points = heapq.heappop(queue)
        state = (i, j, direction)
        if cost >= best.get(state, float('inf')):
            continue
        best[state] = cost
        if (i, j) == destination:
            simplified = [points[0]]
            for p in points[1:]:
                if len(simplified) > 1 and ((simplified[-2][0] == simplified[-1][0] == p[0]) or (simplified[-2][1] == simplified[-1][1] == p[1])):
                    simplified[-1] = p
                else:
                    simplified.append(p)
            return simplified
        for ni, nj, nd in ((i-1, j, 0), (i+1, j, 0), (i, j-1, 1), (i, j+1, 1)):
            if not (0 <= ni < len(xs) and 0 <= nj < len(ys)):
                continue
            a, b = (xs[i], ys[j]), (xs[ni], ys[nj])
            if clear(a, b):
                distance = abs(a[0]-b[0]) + abs(a[1]-b[1])
                heapq.heappush(queue, (cost + distance + (24 if direction >= 0 and direction != nd else 0), (ni, nj), nd, points + [b]))
    raise ValueError(f'No diagram route: {start} to {end}')


def rounded_path(points):
    out = f'M{points[0][0]} {points[0][1]}'
    for i, (x, y) in enumerate(points[1:-1], 1):
        prev, after = points[i-1], points[i+1]
        before_length = abs(x-prev[0]) + abs(y-prev[1])
        after_length = abs(x-after[0]) + abs(y-after[1])
        radius = min(10, before_length / 2, after_length / 2)
        a = (x + (prev[0]-x) * radius / before_length, y + (prev[1]-y) * radius / before_length)
        b = (x + (after[0]-x) * radius / after_length, y + (after[1]-y) * radius / after_length)
        out += f'L{a[0]} {a[1]} Q{x} {y} {b[0]} {b[1]}'
    return out + f'L{points[-1][0]} {points[-1][1]}'
