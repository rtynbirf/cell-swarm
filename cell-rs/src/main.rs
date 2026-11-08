// cell-rs/src/main.rs — клетка cell-swarm на чистом std (ПРЕДЛОЖЕНИЕ-09, волна ×3 W3-D).
// Такт 1 «цепь»: построчная хеш-цепь байтов файла (правило совпадает с golden_exchange.py).
// Такт 2 «конверт»: клетка принимает blood-конверт (поля через аргументы), сверяет значение
// с допуском (eps + deadband) и возвращает канонический verdict JSON — те же байты, что у Python.
// Ноль крейтов: SHA-256 написан вручную по FIPS 180-4. Python 3.11-совместимый эталон —
// cell-rs/golden_exchange.py (hashlib), обмен проверяется байт-в-байт в CI wave3-cell-rs.yml.
use std::env;
use std::fs;
use std::io::Read;
use std::process::exit;

const K: [u32; 64] = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

fn sha256(data: &[u8]) -> [u8; 32] {
    let mut h: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    ];
    let mut msg = data.to_vec();
    let bits = (data.len() as u64).wrapping_mul(8);
    msg.push(0x80);
    while msg.len() % 64 != 56 {
        msg.push(0);
    }
    msg.extend_from_slice(&bits.to_be_bytes());
    for chunk in msg.chunks(64) {
        let mut w = [0u32; 64];
        for i in 0..16 {
            w[i] = u32::from_be_bytes([chunk[4 * i], chunk[4 * i + 1], chunk[4 * i + 2], chunk[4 * i + 3]]);
        }
        for i in 16..64 {
            let s0 = w[i - 15].rotate_right(7) ^ w[i - 15].rotate_right(18) ^ (w[i - 15] >> 3);
            let s1 = w[i - 2].rotate_right(17) ^ w[i - 2].rotate_right(19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16].wrapping_add(s0).wrapping_add(w[i - 7]).wrapping_add(s1);
        }
        let (mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut hh) =
            (h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7]);
        for i in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch = (e & f) ^ ((!e) & g);
            let t1 = hh.wrapping_add(s1).wrapping_add(ch).wrapping_add(K[i]).wrapping_add(w[i]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let t2 = s0.wrapping_add(maj);
            hh = g;
            g = f;
            f = e;
            e = d.wrapping_add(t1);
            d = c;
            c = b;
            b = a;
            a = t1.wrapping_add(t2);
        }
        h[0] = h[0].wrapping_add(a);
        h[1] = h[1].wrapping_add(b);
        h[2] = h[2].wrapping_add(c);
        h[3] = h[3].wrapping_add(d);
        h[4] = h[4].wrapping_add(e);
        h[5] = h[5].wrapping_add(f);
        h[6] = h[6].wrapping_add(g);
        h[7] = h[7].wrapping_add(hh);
    }
    let mut out = [0u8; 32];
    for i in 0..8 {
        out[4 * i..4 * i + 4].copy_from_slice(&h[i].to_be_bytes());
    }
    out
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{:02x}", b)).collect()
}

fn die(msg: &str) -> ! {
    eprintln!("cell-rs: {}", msg);
    exit(2);
}

// Такт 1 «цепь»: h_i = sha256(hex(prev)_ascii + байты_строки); первый prev — 64 нуля.
// Пустые строки (в т.ч. завершающий \n) в цепь не входят; \r у хвоста строки срезается.
fn chain(path: &str) -> String {
    let raw = fs::read(path).unwrap_or_else(|e| die(&format!("chain: файл не читается: {}", e)));
    let mut prev = "0".repeat(64);
    let mut n = 0usize;
    for line in raw.split(|&c| c == b'\n') {
        let mut line = line;
        if line.ends_with(b"\r") {
            line = &line[..line.len() - 1];
        }
        if line.is_empty() {
            continue;
        }
        let mut buf = prev.clone().into_bytes();
        buf.extend_from_slice(line);
        prev = hex(&sha256(&buf));
        n += 1;
    }
    format!("root={} lines={}", prev, n)
}

// Такт 2 «конверт»: сверка с допуском. |delta| <= eps → OK; <= eps+deadband → WARN; иначе HALT.
// delta печатается с фиксированной точностью .6 — байты совпадают с Python (format(d, ".6f")).
fn verdict(value: f64, center: f64, eps: f64, deadband: f64, envelope_hash: &str) -> String {
    let delta = value - center;
    let ad = delta.abs();
    let v = if ad <= eps {
        "OK"
    } else if ad <= eps + deadband {
        "WARN"
    } else {
        "HALT"
    };
    format!(
        "{{\"delta\":\"{:.6}\",\"envelope_hash\":\"{}\",\"verdict\":\"{}\"}}",
        delta, envelope_hash, v
    )
}

fn arg_f64(a: &[String], i: usize) -> f64 {
    if i >= a.len() {
        die("verdict: после флага нет значения");
    }
    match a[i].parse::<f64>() {
        Ok(v) => v,
        Err(_) => die("verdict: значение не число"),
    }
}

fn main() {
    let a: Vec<String> = env::args().collect();
    if a.len() < 2 {
        die("использование: cell-rs chain <файл> | cell-rs verdict --value F --center F --eps F --deadband F --envelope-hash HEX | cell-rs hash-stdin");
    }
    match a[1].as_str() {
        "chain" => {
            if a.len() != 3 {
                die("chain: нужен ровно один путь к файлу");
            }
            println!("{}", chain(&a[2]));
        }
        "verdict" => {
            let (mut val, mut cen, mut eps, mut db) = (0.0f64, 0.0f64, 0.0f64, 0.0f64);
            let mut eh = String::new();
            let mut i = 2;
            while i < a.len() {
                match a[i].as_str() {
                    "--value" => { val = arg_f64(&a, i + 1); i += 2; }
                    "--center" => { cen = arg_f64(&a, i + 1); i += 2; }
                    "--eps" => { eps = arg_f64(&a, i + 1); i += 2; }
                    "--deadband" => { db = arg_f64(&a, i + 1); i += 2; }
                    "--envelope-hash" => {
                        if i + 1 >= a.len() { die("verdict: после --envelope-hash нет значения"); }
                        eh = a[i + 1].clone();
                        i += 2;
                    }
                    _ => die("verdict: незнакомый аргумент"),
                }
            }
            if eh.is_empty() {
                die("verdict: нужен --envelope-hash");
            }
            println!("{}", verdict(val, cen, eps, db, &eh));
        }
        "hash-stdin" => {
            let mut buf = Vec::new();
            std::io::stdin()
                .read_to_end(&mut buf)
                .unwrap_or_else(|e| die(&format!("hash-stdin: stdin не читается: {}", e)));
            println!("{}", hex(&sha256(&buf)));
        }
        _ => die("незнакомая команда: chain | verdict | hash-stdin"),
    }
}
