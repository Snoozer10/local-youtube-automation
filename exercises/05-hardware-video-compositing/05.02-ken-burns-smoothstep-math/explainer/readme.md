# Explainer: Cubic Hermite Smoothstep Mathematics & Pacing

## 1. Smoothstep Derivation & Boundary Conditions
Linear motion $f(t) = t$ has a non-zero constant velocity $f'(t) = 1$. At $t = 0$ and $t = 1$, the velocity instantly changes from $0$ to $1$ and from $1$ to $0$, causing infinite acceleration (impulse jerk).

To eliminate camera jerk, we seek a cubic polynomial $S(t) = at^3 + bt^2 + ct + d$ satisfying four boundary constraints:
1. $S(0) = 0$ (Start at initial position)
2. $S(1) = 1$ (End at final position)
3. $S'(0) = 0$ (Zero starting velocity)
4. $S'(1) = 0$ (Zero ending velocity)

Solving this system of linear equations:
- From (1): $d = 0$
- $S'(t) = 3at^2 + 2bt + c$
- From (3): $c = 0$
- From (2): $a + b = 1 \implies b = 1 - a$
- From (4): $3a + 2b = 0 \implies 3a + 2(1 - a) = 0 \implies a = -2$, therefore $b = 3$.

Thus, the canonical Cubic Hermite Smoothstep equation is:
$$S(t) = 3t^2 - 2t^3 = t^2(3 - 2t)$$

Its derivative:
$$S'(t) = 6t - 6t^2 = 6t(1 - t)$$
This exhibits a smooth parabolic bell curve, reaching maximum velocity of $1.5$ at $t = 0.5$ and tapering gently to $0$ at both ends.

## 2. In-Filter FFmpeg Implementation
Inside the FFmpeg `zoompan` filter, frames are counted with the 1-based variable `on` ($1 \le on \le frames$).
The normalized progress $t$ is expressed as:
```text
t = ((on-1)/(frames-1))
ease = (((on-1)/(frames-1))*((on-1)/(frames-1))*(3-2*((on-1)/(frames-1))))
```
This expression is evaluated dynamically by FFmpeg's internal expression evaluator on each frame without CPU round-trips.

## 3. Speech-Paced Zoom Modulation
Static slides can feel disconnected from energetic or emotional narration. The pipeline couples camera movement to speech tempo:
- Baseline speech rate is calibrated to $3.0\text{ words/sec}$.
- Pacing ratio:
  $$\text{pace\_ratio} = \text{clamp}\left(\frac{\text{wps}}{3.0}, 0.75, 1.35\right)$$
- If dynamic scaling is active, the effective maximum zoom is modulated:
  $$\text{effective\_zoom\_max} = \min(1.15, \text{zoom\_min} + (\text{zoom\_max} - \text{zoom\_min}) \times \text{pace\_ratio})$$
Fast narration produces punchy, dynamic zooms, while slow explanatory narration receives gentle, subtle drifts.
