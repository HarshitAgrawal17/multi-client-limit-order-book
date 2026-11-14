# Multi-client limit order book

A limit order book for **multiple clients**, written in plain Python with **no imports**. Orders are matched by **price-time priority**, every client has an **isolated portfolio**, and the book is built on a binary search tree in which each node stores the size of its subtree.

It extends the single-client order book I built for a data-structures course, and the data structure here was written from scratch.

## Features

- Clients with isolated portfolios: cash, units and reserved cash
- Limit buy orders (one unit each); the cash behind a bid is locked until it fills or is cancelled
- Market sell orders, matched highest price first, then earliest timestamp
- Order cancellation with refund
- Self-trade prevention: a seller never trades against their own bid
- Queries: open bids inside a price range and time range, active prices, timestamps at a price, a client's open orders
- Built-in randomized self-test against brute-force models, including a check that cash and units are conserved

## How it works

| Piece | Role |
| --- | --- |
| `SizeTree` | Binary search tree where every node stores its subtree size, giving rank, k-th smallest and range counts in O(H) |
| price tree | One `SizeTree` holding the active price levels |
| level trees | One `SizeTree` of timestamps for every price level |
| `owner` map | Maps each open order `(price, timestamp)` to the client who placed it |
| `Portfolio` | Per-client cash, units and reserved cash |

A market sell repeatedly takes the maximum price from the price tree and the minimum timestamp from that level, which gives price-time priority. Empty price levels are removed.

## Complexity

H is the height of the tree. The tree does not rebalance, so H is O(log N) for random input and O(N) in the worst case.

| Operation | Cost |
| --- | --- |
| `place_limit_order` | O(H) |
| `cancel_order` | O(H) |
| `market_sell` | O(H) per fill |
| `liquidity(p_low, p_high, t_start, t_end)` | O(k * H), where k is the number of price levels in the price range |
| `SizeTree` rank, range count, k-th smallest | O(H) |

## Usage

```python
from limit_order_book import MultiClientOrderBook

book = MultiClientOrderBook()
book.register_client("alice", cash=1000)
book.register_client("bob", cash=1000)
book.register_client("carol", units=5)

book.place_limit_order("alice", 100, 1)   # client, price, timestamp
book.place_limit_order("bob", 100, 2)     # same price, later: alice has priority
book.place_limit_order("bob", 105, 3)     # better price: matched first

print(book.market_sell("carol", 2))
# [('bob', 105, 3), ('alice', 100, 1)]
print(book.portfolio("carol"))
# {'cash': 205, 'units': 3, 'reserved': 0}
```

Run the demo and the self-test (300 randomized runs each for the tree and the book):

```
python3 limit_order_book.py
```

## Design choices and limitations

- Every order is for one unit, and the book holds bids only (market sells hit the bids).
- A market sell stops early when the seller has no units left, the book is empty, or the best bid is the seller's own.
- The tree is not self-balancing; a red-black or AVL tree would guarantee O(log N).
- Everything is in memory; there is no persistence or concurrency.
