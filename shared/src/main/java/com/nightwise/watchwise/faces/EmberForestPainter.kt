package com.nightwise.watchwise.faces

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import java.time.ZonedDateTime
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * 05 · Ember Forest — pixel-art campfire ("Pixel Art AMOLED Watch Faces" design).
 *
 * A 150 x 150 pixel grid scaled up without smoothing: pines, a tent and a camper around a
 * fire with rising smoke and embers, the time in a 5x7 pixel font, and a 10-step "move" bar
 * (one block per 1,000 steps) with the battery level.
 *
 * Ambient: only a row of embers, the log, the time and the date.
 *
 * Same drawing as tools/gen_watchfaces.py (the WFF face): no glow flicker, a 5.2 s fire
 * loop, stars that blink on whole seconds. [accent] is the flame colour.
 */
class EmberForestPainter : FacePainter {

    private val px = IntArray(N * N)
    private val argb = IntArray(N * N)
    private val bitmap: Bitmap = Bitmap.createBitmap(N, N, Bitmap.Config.ARGB_8888)
    private val paint = Paint() // no filtering: keep the pixels sharp
    private val src = Rect(0, 0, N, N)

    /** The still scene (glow, pines, tent, camper, logs), drawn once. */
    private val scene = IntArray(N * N).also { drawScene(it) }

    override fun draw(
        canvas: Canvas,
        bounds: Rect,
        time: ZonedDateTime,
        data: FaceData,
        accent: Int,
        ambient: Boolean,
    ) {
        val t = (time.toInstant().toEpochMilli() % (LOOP_MS)) / 1000.0
        if (ambient) {
            px.fill(0)
            for (i in -6..6) {
                if (sin(i * 1.3) > 0) set(px, FX + i, FB - 1 - (if (i % 2 == 0) 1 else 0), if (i % 3 == 0) 8 else 7)
            }
            line(px, 64, 113, 86, 110, 12)
        } else {
            px.fill(0)
            for ((x, y, phase) in STARS) if ((time.second + phase) % 4 < 2) set(px, x, y, 17)
            for (i in scene.indices) if (scene[i] != 0) px[i] = scene[i]
            drawFire(px, t)
        }

        val hm = "${time.displayHour(data.is24Hour).pad2()}:${time.minute.pad2()}"
        if (!ambient) text(px, hm, TIME_X + 1, 22, 3, 3, true)
        text(px, hm, TIME_X, 21, if (ambient) 2 else 1, 3, true)
        val date = "${DAYS_FULL[time.dayOfWeek.value % 7]} ${time.dayOfMonth.pad2()} ${time.monthShort()}"
        ctext(px, date, 46, 2)
        if (!ambient) {
            rect(px, 36, 125, 78, 16, 0)
            val moves = ((data.steps ?: 0) / 1000).coerceIn(0, 10)
            for (s in 0 until 10) rect(px, 46 + s * 6, 127, 4, 2, if (s < moves) 8 else 22)
            ctext(px, "MOVE $moves/10 · ${data.battery}%", 132, 2)
        }

        // Palette -> pixels, clipped to the round screen like the design.
        val r = N / 2.0
        for (y in 0 until N) {
            val dy = y + 0.5 - r
            val hw = sqrt(max(0.0, r * r - dy * dy))
            val x0 = ceil(r - hw - 0.5).toInt()
            val x1 = floor(r + hw - 0.5).toInt()
            for (x in 0 until N) {
                val i = y * N + x
                argb[i] = if (x in x0..x1) (if (px[i] == 8) accent else PALETTE[px[i]]) else Color.BLACK
            }
        }
        bitmap.setPixels(argb, 0, N, 0, 0, N, N)
        canvas.drawColor(Color.BLACK)
        canvas.drawBitmap(bitmap, src, bounds, paint)
    }

    private fun drawScene(b: IntArray) {
        for (y in 78 until N) for (x in 0 until N) {
            val ground = y >= 106
            val d = if (ground) hypot((x - FX) / 1.9, (y - FB) * 1.2) else hypot((x - FX).toDouble(), (y - FB) * 0.9) * 1.6
            val v = max(0.0, 3 - d / 12)
            val base = floor(v).toInt()
            val lvl = min(3, base + if (dith(x, y, v - base)) 1 else 0)
            if (lvl > 0) set(b, x, y, 3 + lvl)
        }
        fun pine(bx: Int, by: Int, h: Int) {
            for (j in 0 until h) {
                val w = floor((j % 6) * 0.7 + j * 0.22).toInt()
                rect(b, bx - w, by - h + j, w * 2 + 1, 1, 14)
                val ex = if (bx < FX) bx + w else bx - w
                if (abs(ex - FX) < 58 && j > 2) set(b, ex, by - h + j, 15)
            }
            rect(b, bx, by, 2, 3, 14)
        }
        listOf(
            Triple(6, 104, 30), Triple(16, 106, 42), Triple(27, 104, 26), Triple(124, 104, 28),
            Triple(134, 106, 44), Triple(145, 105, 30), Triple(3, 108, 22), Triple(148, 108, 20),
        ).forEach { (x, y, h) -> pine(x, y, h) }
        for (j in 0..22) {
            val hw = floor(j * 0.7).toInt()
            for (i in -hw..hw) {
                val door = j > 10 && abs(i) < (j - 10) * 0.45
                set(b, 114 + i, 90 + j, if (door) 0 else if (i < 0) 19 else 18)
            }
        }
        line(b, 114, 88, 114, 90, 18)
        CAMPER.forEachIndexed { j, row ->
            val last = row.lastIndexOf('#')
            row.forEachIndexed { i, ch ->
                if (ch == '#') set(b, 36 + i, 96 + j, if (i >= last - (if (j in 5..8) 1 else 0)) 21 else 20)
            }
        }
        rect(b, 32, 110, 18, 3, 12)
        rect(b, 32, 110, 18, 1, 13)
        for (w in 0 until 3) {
            line(b, 62, 115 + w, 86, 109 + w, if (w == 0) 13 else 11)
            line(b, 64, 108 + w, 88, 114 + w, if (w == 0) 13 else 11)
        }
        rect(b, 61, 115, 2, 3, 12)
        rect(b, 87, 114, 2, 3, 12)
    }

    /** Smoke, flame, flame bits and embers; frequencies fit the [LOOP] s loop. */
    private fun drawFire(b: IntArray, t: Double) {
        for (i in 0 until 6) {
            val age = (t / LOOP + i / 6.0) % 1
            val cx = FX + sin(age * 4 + i) * 6 + age * 12
            val cy = FB - 28 - age * 52
            val r = 2 + age * 7
            var yy = -r
            while (yy <= r) {
                var xx = -r
                while (xx <= r) {
                    if (xx * xx + yy * yy <= r * r) {
                        val px = jround(cx + xx)
                        val py = jround(cy + yy)
                        if (get(b, px, py) == 0 && dith(px, py, 0.32 * (1 - age))) set(b, px, py, 16)
                    }
                    xx += 1
                }
                yy += 1
            }
        }
        for (x in -11..11) {
            val hMax = 24 * max(0.0, 1 - abs(x) / 12.0).pow(1.2)
            val h = hMax * (0.72 + 0.22 * sin(t * 9 * W + x * 1.7) + 0.16 * sin(t * 14 * W + x * 0.6))
            var y = 0
            while (y < h) {
                val rel = y / h
                val px = FX + x + jround(sin(t * 5 * W + y * 0.35) * rel * 2)
                val py = FB - 2 - y
                y++
                if (rel > 0.86 && !dith(px, py, 0.5)) continue
                val core = 5 * (1 - rel * 1.1)
                val c = when {
                    abs(x) < core * 0.55 && rel < 0.4 -> 10
                    abs(x) < core && rel < 0.6 -> 9
                    rel < 0.78 -> 8
                    else -> 7
                }
                set(b, px, py, c)
            }
        }
        for (k in 0 until 3) {
            val a = (t * 8 / LOOP + k * 0.33) % 1
            val bx = FX + intArrayOf(-4, 2, 6)[k] + jround(sin(t * 4 * W + k) * 2)
            if (a < 0.7) rect(b, bx, jround(FB - 22 - a * 12), 2, 3, if (a < 0.35) 8 else 7)
        }
        for (i in 0 until 18) {
            val age = (t * 2 / LOOP + hash(i, 4)) % 1
            val x = FX + (hash(i, 7) - 0.5) * 10 + sin(age * 7 + i) * 5 * age + age * 8 * (hash(i, 8) - 0.3)
            val y = FB - 10 - age * 78
            val c = when {
                age < 0.25 -> 10
                age < 0.45 -> 9
                age < 0.7 -> 8
                age < 0.9 -> 7
                else -> 0
            }
            if (c != 0) {
                set(b, x, y, c)
                if (i % 4 == 0) set(b, x, y + 1, 7)
            }
        }
    }

    // ---- the design's pixel engine

    private fun set(b: IntArray, x: Number, y: Number, c: Int) {
        val ix = jround(x.toDouble())
        val iy = jround(y.toDouble())
        if (ix in 0 until N && iy in 0 until N) b[iy * N + ix] = c
    }

    private fun get(b: IntArray, x: Int, y: Int) = if (x in 0 until N && y in 0 until N) b[y * N + x] else 0

    private fun rect(b: IntArray, x: Int, y: Int, w: Int, h: Int, c: Int) {
        for (j in 0 until h) for (i in 0 until w) set(b, x + i, y + j, c)
    }

    private fun line(b: IntArray, x0: Int, y0: Int, x1: Int, y1: Int, c: Int) {
        val s = max(abs(x1 - x0), abs(y1 - y0)).coerceAtLeast(1)
        for (i in 0..s) set(b, x0 + (x1 - x0) * i / s.toDouble(), y0 + (y1 - y0) * i / s.toDouble(), c)
    }

    private fun text(b: IntArray, str: String, x: Int, y: Int, c: Int, s: Int = 1, big: Boolean = false) {
        var cx = x
        for (ch in str) {
            val rows = glyph(ch, big)
            rows.forEachIndexed { j, row ->
                row.forEachIndexed { i, p -> if (p == '#') rect(b, cx + i * s, y + j * s, s, s, c) }
            }
            cx += (rows[0].length + 1) * s
        }
    }

    private fun ctext(b: IntArray, str: String, y: Int, c: Int) =
        text(b, str, jround((N - textWidth(str, 1, false)) / 2.0), y, c)

    private companion object {
        const val N = 150
        const val FX = 75
        const val FB = 112
        const val LOOP = 5.2
        const val LOOP_MS = 5200L
        const val W = 2 * Math.PI / LOOP

        val DAYS_FULL = arrayOf("SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY")

        val PALETTE = intArrayOf(
            0x000000, 0xffe2b8, 0xd9925a, 0x2a1206, 0x160703, 0x2e1004, 0x521c06, 0xff3d00, 0xff8a00, 0xffd23f,
            0xfff4c8, 0x7a4a22, 0x3e220e, 0xc9773a, 0x050a08, 0x7a3010, 0x1f1c1b, 0xb9b2a0, 0x1e2a3c, 0xa84c22,
            0x0c0806, 0xd06a2a, 0x2a1408,
        ).map { it or 0xFF000000.toInt() }.toIntArray()

        val CAMPER = listOf(
            "...###....", "..#####...", "..#####...", "...###....", "..#####...", ".#######..", ".########.",
            ".#######..", "..######..", "..#####...", "..######..", "..##..###.", "..##...##.", ".###..###.",
        )

        val SMALL = mapOf(
            'A' to ".#. #.# ### #.# #.#", 'B' to "##. #.# ##. #.# ##.", 'C' to ".## #.. #.. #.. .##",
            'D' to "##. #.# #.# #.# ##.", 'E' to "### #.. ##. #.. ###", 'F' to "### #.. ##. #.. #..",
            'G' to ".## #.. #.# #.# .##", 'H' to "#.# #.# ### #.# #.#", 'I' to "### .#. .#. .#. ###",
            'J' to "..# ..# ..# #.# .#.", 'K' to "#.# #.# ##. #.# #.#", 'L' to "#.. #.. #.. #.. ###",
            'M' to "#.# ### ### #.# #.#", 'N' to "##. #.# #.# #.# #.#", 'O' to ".#. #.# #.# #.# .#.",
            'P' to "##. #.# ##. #.. #..", 'Q' to ".#. #.# #.# ##. .##", 'R' to "##. #.# ##. #.# #.#",
            'S' to ".## #.. .#. ..# ##.", 'T' to "### .#. .#. .#. .#.", 'U' to "#.# #.# #.# #.# ###",
            'V' to "#.# #.# #.# #.# .#.", 'W' to "#.# #.# ### ### #.#", 'X' to "#.# #.# .#. #.# #.#",
            'Y' to "#.# #.# .#. .#. .#.", 'Z' to "### ..# .#. #.. ###",
            '0' to "### #.# #.# #.# ###", '1' to ".#. ##. .#. .#. ###", '2' to "##. ..# .#. #.. ###",
            '3' to "##. ..# .#. ..# ##.", '4' to "#.# #.# ### ..# ..#", '5' to "### #.. ##. ..# ##.",
            '6' to ".## #.. ### #.# ###", '7' to "### ..# .#. .#. .#.", '8' to "### #.# ### #.# ###",
            '9' to "### #.# ### ..# ##.",
            ':' to ". # . # .", '%' to "#.# ..# .#. #.. #.#", '/' to "..# ..# .#. #.. #..", '.' to ". . . . #",
            '-' to "... ... ### ... ...", ' ' to ".. .. .. .. ..", '·' to ". . # . .", '°' to "##. ##. ... ... ...",
        ).mapValues { it.value.split(' ') }

        val BIG = mapOf(
            '0' to ".###. #...# #..## #.#.# ##..# #...# .###.", '1' to "..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.",
            '2' to ".###. #...# ....# ..##. .#... #.... #####", '3' to "####. ....# ....# .###. ....# ....# ####.",
            '4' to "...#. ..##. .#.#. #..#. ##### ...#. ...#.", '5' to "##### #.... ####. ....# ....# #...# .###.",
            '6' to "..##. .#... #.... ####. #...# #...# .###.", '7' to "##### ....# ...#. ..#.. .#... .#... .#...",
            '8' to ".###. #...# #...# .###. #...# #...# .###.", '9' to ".###. #...# #...# .#### ....# ...#. .##..",
            ':' to ". . # . # . .",
        ).mapValues { it.value.split(' ') }

        fun glyph(ch: Char, big: Boolean): List<String> =
            (if (big) BIG[ch] else null) ?: SMALL[ch] ?: SMALL.getValue(' ')

        fun textWidth(str: String, s: Int, big: Boolean) = str.sumOf { (glyph(it, big)[0].length + 1) * s } - s

        val TIME_X = jround((N - textWidth("00:00", 3, true)) / 2.0)

        /** The design's stars (x, y, blink phase in seconds), minus the ones behind the time. */
        val STARS: List<Triple<Int, Int, Int>> = (0 until 30).mapNotNull { i ->
            val x = floor(hash(i, 1) * N).toInt()
            val y = floor(hash(i, 2) * 70).toInt()
            if (y in 15..51 && x in 29..121) null else Triple(x, y, jround(i * 2.1 / 1.5) % 4)
        }

        private val BAYER = intArrayOf(0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5)

        fun dith(x: Int, y: Int, t: Double) = t * 16 > BAYER[(y and 3) * 4 + (x and 3)]

        /** JavaScript Math.round. */
        fun jround(v: Double) = floor(v + 0.5).toInt()

        fun hash(a: Int, b: Int): Double {
            val v = sin(a * 127.1 + b * 311.7) * 43758.5453
            return v - floor(v)
        }
    }
}
