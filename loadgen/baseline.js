// k6 run -e BASE_URL=http://<vm-ip> -e DURATION=10m loadgen/baseline.js
//
// Open model (arrival rate, not VU count) so a slow backend shows up as latency
// and dropped iterations instead of quietly lowering the request rate.
import http from "k6/http";
import { check } from "k6";

const BASE = __ENV.BASE_URL || "http://localhost:8080";
const DURATION = __ENV.DURATION || "5m";
const PRODUCTS = ["yirgacheffe", "huila", "kiambu", "decaf"];
const JSON_HEADERS = { "content-type": "application/json" };

export const options = {
  scenarios: {
    browse: {
      executor: "constant-arrival-rate",
      exec: "browse",
      rate: 8,
      timeUnit: "1s",
      duration: DURATION,
      preAllocatedVUs: 10,
    },
    checkout: {
      executor: "constant-arrival-rate",
      exec: "checkout",
      rate: 2,
      timeUnit: "1s",
      duration: DURATION,
      preAllocatedVUs: 5,
    },
    // a trickle of bad input so 4xx handling shows up in the data
    junk: {
      executor: "constant-arrival-rate",
      exec: "junk",
      rate: 1,
      timeUnit: "10s",
      duration: DURATION,
      preAllocatedVUs: 1,
    },
  },
  summaryTrendStats: ["avg", "p(50)", "p(90)", "p(95)", "p(99)", "max"],
};

export function browse() {
  const res = http.get(`${BASE}/products`, { tags: { name: "products" } });
  check(res, { "products 200": (r) => r.status === 200 });
}

export function checkout() {
  const body = JSON.stringify({
    product_id: PRODUCTS[Math.floor(Math.random() * PRODUCTS.length)],
    quantity: 1 + Math.floor(Math.random() * 3),
  });
  const res = http.post(`${BASE}/checkout`, body, {
    headers: JSON_HEADERS,
    tags: { name: "checkout" },
  });
  check(res, { "checkout 202": (r) => r.status === 202 });
}

export function junk() {
  const res = http.post(`${BASE}/checkout`, JSON.stringify({ product_id: "espresso-machine", quantity: 1 }), {
    headers: JSON_HEADERS,
    tags: { name: "checkout_invalid" },
  });
  check(res, { "invalid rejected": (r) => r.status === 422 });
}
