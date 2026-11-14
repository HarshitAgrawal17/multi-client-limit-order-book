"""Multi-client limit order book, written from scratch with no imports.

Data structures
---------------
* SizeTree: a binary search tree where every node stores the size of its
  subtree. That one extra field gives O(H) rank, k-th smallest and
  range-count queries (H = tree height; the tree is not self-balancing).
* The book keeps one SizeTree of active prices, plus one SizeTree of
  timestamps for every price level.

Matching rule: highest price first, then earliest timestamp (price-time
priority). Every order is for one unit. Each client has an isolated
Portfolio; cash backing an open bid is locked until it fills or is cancelled.

Run this file directly to execute the built-in self-test.
"""


# =====================================================================
# Size-augmented binary search tree
# =====================================================================
class _Node:
    __slots__ = ("key", "left", "right", "parent", "size")

    def __init__(self, key, parent=None):
        self.key = key
        self.left = None
        self.right = None
        self.parent = parent
        self.size = 1


class SizeTree:
    def __init__(self):
        self.root = None

    def __len__(self):
        return self.root.size if self.root else 0

    # ---- lookup ------------------------------------------------------
    def _find(self, key):
        node = self.root
        while node is not None and node.key != key:
            node = node.left if key < node.key else node.right
        return node

    def contains(self, key):
        return self._find(key) is not None

    def min_key(self):
        node = self.root
        if node is None:
            return None
        while node.left is not None:
            node = node.left
        return node.key

    def max_key(self):
        node = self.root
        if node is None:
            return None
        while node.right is not None:
            node = node.right
        return node.key

    # ---- insert / remove ---------------------------------------------
    def insert(self, key):
        """Insert key; return False (and change nothing) if already present."""
        if self.contains(key):
            return False
        if self.root is None:
            self.root = _Node(key)
            return True
        node = self.root
        while True:
            node.size += 1                       # key will land in this subtree
            if key < node.key:
                if node.left is None:
                    node.left = _Node(key, node)
                    return True
                node = node.left
            else:
                if node.right is None:
                    node.right = _Node(key, node)
                    return True
                node = node.right

    def remove(self, key):
        """Remove key; return False if it was not present."""
        node = self._find(key)
        if node is None:
            return False
        if node.left is not None and node.right is not None:
            heir = node.right                    # in-order successor
            while heir.left is not None:
                heir = heir.left
            node.key = heir.key                  # move its key up ...
            node = heir                          # ... and delete that node instead
        child = node.left if node.left is not None else node.right
        parent = node.parent
        if child is not None:
            child.parent = parent
        if parent is None:
            self.root = child
        elif parent.left is node:
            parent.left = child
        else:
            parent.right = child
        while parent is not None:                # fix sizes up to the root
            parent.size -= 1
            parent = parent.parent
        return True

    # ---- order-statistic queries -------------------------------------
    def count_less(self, x):
        """Number of keys strictly less than x."""
        total, node = 0, self.root
        while node is not None:
            if node.key < x:
                total += 1 + (node.left.size if node.left else 0)
                node = node.right
            else:
                node = node.left
        return total

    def count_at_most(self, x):
        """Number of keys less than or equal to x."""
        total, node = 0, self.root
        while node is not None:
            if node.key <= x:
                total += 1 + (node.left.size if node.left else 0)
                node = node.right
            else:
                node = node.left
        return total

    def count_range(self, low, high):
        """Number of keys k with low <= k <= high, in O(H)."""
        if high < low:
            return 0
        return self.count_at_most(high) - self.count_less(low)

    def kth_smallest(self, k):
        """k-th smallest key (1-indexed), or None if k is out of range."""
        if k < 1 or k > len(self):
            return None
        node = self.root
        while True:
            left = node.left.size if node.left else 0
            if k <= left:
                node = node.left
            elif k == left + 1:
                return node.key
            else:
                k -= left + 1
                node = node.right

    # ---- ordered traversal (iterative) -------------------------------
    def keys(self):
        return self.keys_in_range(None, None)

    def keys_in_range(self, low, high):
        """Keys in [low, high], ascending. None means unbounded on that side."""
        out, stack, node = [], [], self.root
        while stack or node is not None:
            while node is not None:
                if low is not None and node.key < low:
                    node = node.right            # whole left side is below range
                else:
                    stack.append(node)
                    node = node.left
            if not stack:
                break
            node = stack.pop()
            if high is not None and node.key > high:
                break
            out.append(node.key)
            node = node.right
        return out


# =====================================================================
# Clients and the order book
# =====================================================================
class Portfolio:
    def __init__(self, cash, units):
        self.cash = cash
        self.units = units
        self.reserved = 0        # cash locked behind this client's open bids


class MultiClientOrderBook:
    def __init__(self):
        self.prices = SizeTree()       # active price levels
        self.levels = {}               # price -> SizeTree of timestamps
        self.owner = {}                # (price, timestamp) -> client id
        self.portfolios = {}           # client id -> Portfolio
        self.open_orders = {}          # client id -> set of (price, timestamp)

    # ---- clients -----------------------------------------------------
    def register_client(self, client, cash=0, units=0):
        if client in self.portfolios:
            raise ValueError("client already registered")
        self.portfolios[client] = Portfolio(cash, units)
        self.open_orders[client] = set()

    def portfolio(self, client):
        p = self.portfolios[client]
        return {"cash": p.cash, "units": p.units, "reserved": p.reserved}

    # ---- limit orders: bid for one unit at 'price' -------------------
    def place_limit_order(self, client, price, timestamp):
        p = self.portfolios[client]
        if (price, timestamp) in self.owner:
            raise ValueError("an order with this price and timestamp already exists")
        if p.cash < price:
            raise ValueError("insufficient cash")
        p.cash -= price
        p.reserved += price
        self.prices.insert(price)
        level = self.levels.get(price)
        if level is None:
            level = self.levels[price] = SizeTree()
        level.insert(timestamp)
        self.owner[(price, timestamp)] = client
        self.open_orders[client].add((price, timestamp))

    def cancel_order(self, client, price, timestamp):
        if self.owner.get((price, timestamp)) != client:
            raise ValueError("no such open order for this client")
        self._remove_order(price, timestamp)
        p = self.portfolios[client]
        p.reserved -= price
        p.cash += price

    def _remove_order(self, price, timestamp):
        level = self.levels[price]
        level.remove(timestamp)
        if len(level) == 0:                      # drop empty price levels
            self.prices.remove(price)
            del self.levels[price]
        client = self.owner.pop((price, timestamp))
        self.open_orders[client].discard((price, timestamp))

    # ---- market sell order -------------------------------------------
    def market_sell(self, seller, quantity):
        """Sell up to 'quantity' units into the best bids.

        Stops early if the seller has no units left, the book is empty, or the
        best bid belongs to the seller (self-trade prevention).
        Returns the fills as a list of (buyer, price, timestamp)."""
        s = self.portfolios[seller]
        fills = []
        while quantity > 0 and s.units > 0:
            price = self.prices.max_key()
            if price is None:
                break
            timestamp = self.levels[price].min_key()
            buyer = self.owner[(price, timestamp)]
            if buyer == seller:
                break
            self._remove_order(price, timestamp)
            b = self.portfolios[buyer]
            b.reserved -= price                  # locked cash goes to the seller
            b.units += 1
            s.units -= 1
            s.cash += price
            fills.append((buyer, price, timestamp))
            quantity -= 1
        return fills

    # ---- queries -----------------------------------------------------
    def liquidity(self, p_low, p_high, t_start, t_end):
        """Open bids with p_low <= price <= p_high and t_start <= time <= t_end.
        Cost: O(k * H) for the k price levels inside the price range."""
        total = 0
        for price in self.prices.keys_in_range(p_low, p_high):
            total += self.levels[price].count_range(t_start, t_end)
        return total

    def active_prices(self):
        return self.prices.keys()

    def active_timestamps(self, price):
        level = self.levels.get(price)
        return level.keys() if level else []

    def orders_of(self, client):
        return sorted(self.open_orders[client])


# =====================================================================
# Self-test (no imports: a tiny linear congruential generator stands in
# for the random module). Run:  python3 limit_order_book.py
# =====================================================================
class _Rng:
    def __init__(self, seed):
        self.state = seed * 2654435761 % (1 << 32) or 1

    def below(self, n):                           # integer in [0, n)
        self.state = (self.state * 1103515245 + 12345) % (1 << 31)
        return (self.state >> 8) % n

    def between(self, a, b):                      # integer in [a, b]
        return a + self.below(b - a + 1)


def _test_tree(seed):
    rng, tree, ref = _Rng(seed), SizeTree(), set()
    for _ in range(300):
        x = rng.between(1, 60)
        if rng.below(3):
            assert tree.insert(x) == (x not in ref)
            ref.add(x)
        else:
            assert tree.remove(x) == (x in ref)
            ref.discard(x)
        ordered = sorted(ref)
        assert tree.keys() == ordered and len(tree) == len(ref)
        lo, hi = sorted((rng.between(0, 61), rng.between(0, 61)))
        assert tree.count_range(lo, hi) == sum(1 for k in ref if lo <= k <= hi)
        assert tree.count_less(x) == sum(1 for k in ref if k < x)
        assert tree.keys_in_range(lo, hi) == [k for k in ordered if lo <= k <= hi]
        k = rng.between(0, len(ref) + 1)
        assert tree.kth_smallest(k) == (ordered[k - 1] if 1 <= k <= len(ref) else None)
        assert tree.min_key() == (ordered[0] if ordered else None)
        assert tree.max_key() == (ordered[-1] if ordered else None)


def _test_book(seed):
    rng = _Rng(seed)
    names = ["A", "B", "C", "D"]
    start_cash, start_units = 10000, 50
    book = MultiClientOrderBook()
    ref = {}                                              # (price, ts) -> client
    mine = {c: [start_cash, start_units, 0] for c in names}   # cash, units, reserved
    for c in names:
        book.register_client(c, start_cash, start_units)

    for _ in range(400):
        op = rng.below(6)
        if op <= 2:                                       # place a bid
            c, price, ts = names[rng.below(4)], rng.between(1, 30), rng.between(1, 60)
            if (price, ts) in ref:
                try:
                    book.place_limit_order(c, price, ts)
                    raise AssertionError("duplicate order accepted")
                except ValueError:
                    pass
            else:
                book.place_limit_order(c, price, ts)
                ref[(price, ts)] = c
                mine[c][0] -= price
                mine[c][2] += price
        elif op == 3:                                     # market sell
            s, q = names[rng.below(4)], rng.between(1, 6)
            got = book.market_sell(s, q)
            want, left = [], q
            while left > 0 and mine[s][1] > 0 and ref:
                top = max(p for p, _ in ref)
                best = (top, min(t for p, t in ref if p == top))
                if ref[best] == s:
                    break
                buyer = ref.pop(best)
                want.append((buyer, best[0], best[1]))
                mine[buyer][2] -= best[0]
                mine[buyer][1] += 1
                mine[s][1] -= 1
                mine[s][0] += best[0]
                left -= 1
            assert got == want, (got, want)
        elif op == 4 and ref:                             # cancel a bid
            key = sorted(ref)[rng.below(len(ref))]
            c = ref.pop(key)
            book.cancel_order(c, key[0], key[1])
            mine[c][2] -= key[0]
            mine[c][0] += key[0]
        else:                                             # liquidity query
            pl, ph = sorted((rng.between(1, 30), rng.between(1, 30)))
            tl, th = sorted((rng.between(1, 60), rng.between(1, 60)))
            want = sum(1 for (p, t) in ref if pl <= p <= ph and tl <= t <= th)
            assert book.liquidity(pl, ph, tl, th) == want

        assert book.active_prices() == sorted({p for p, _ in ref})
        for c in names:
            p = book.portfolio(c)
            assert [p["cash"], p["units"], p["reserved"]] == mine[c]
            assert book.orders_of(c) == sorted(k for k, v in ref.items() if v == c)
        # conservation: cash and units are never created or destroyed
        assert sum(p["cash"] + p["reserved"] for p in map(book.portfolio, names)) == 4 * start_cash
        assert sum(p["units"] for p in map(book.portfolio, names)) == 4 * start_units


def _demo():
    book = MultiClientOrderBook()
    book.register_client("alice", cash=1000)
    book.register_client("bob", cash=1000)
    book.register_client("carol", units=5)
    book.place_limit_order("alice", 100, 1)
    book.place_limit_order("bob", 100, 2)     # same price, later: alice has priority
    book.place_limit_order("bob", 105, 3)     # better price: matched first
    print("fills:", book.market_sell("carol", 2))
    for name in ("alice", "bob", "carol"):
        print(" ", name, book.portfolio(name))


def self_test():
    for seed in range(1, 301):
        _test_tree(seed)
        _test_book(seed)
    print("self-test passed: 300 randomized runs each for the tree and the book")


if __name__ == "__main__":
    _demo()
    self_test()
