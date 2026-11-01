"""Built-in tutorials: fixed code with explanations, ordered by level."""
from models import Section, Snippet

BINARY_SEARCH = Snippet(
    level="Intermediate",
    complexity="O(log n) time, O(1) space",
    title="Binary search",
    language="Python",
    overview="Finds a value in a sorted list by repeatedly halving the range that could "
             "contain it. Each step discards half the remaining items, so it needs at most "
             "about log2(n) comparisons.",
    code='''def binary_search(items, target):
    low = 0
    high = len(items) - 1

    while low <= high:
        mid = (low + high) // 2
        if items[mid] == target:
            return mid
        elif items[mid] < target:
            low = mid + 1
        else:
            high = mid - 1

    return -1


numbers = [2, 5, 8, 12, 16, 23, 38, 56, 72, 91]
print(binary_search(numbers, 23))''',
    sections=[
        Section(1, 1, "Function signature",
                "`def` defines a function that takes a sorted list `items` and the value "
                "`target` we are looking for.", ["functions"]),
        Section(2, 3, "Set up the search window",
                "`low` and `high` mark the first and last index that could still hold the "
                "target. `len(items) - 1` is the last valid index.", ["indexes"]),
        Section(5, 6, "Loop and find the middle",
                "Keep going while the window isn't empty. `//` is integer division, so `mid` "
                "is always a whole-number index halfway between low and high.",
                ["while loop", "integer division"]),
        Section(7, 8, "Found it",
                "If the middle item is the target we're done, so return its index.",
                ["early return"]),
        Section(9, 12, "Throw away half",
                "If the middle item is too small, the target must be to the right, so move "
                "`low` past `mid`. Otherwise it's to the left, so move `high` before `mid`.",
                ["divide and conquer"]),
        Section(14, 14, "Not found",
                "If the window became empty, the target isn't in the list. Returning -1 is a "
                "common way to say \"not found\".", ["sentinel value"]),
        Section(17, 18, "Try it out",
                "Build a sorted list and search it. 23 is at index 5, so this prints 5.",
                ["testing"]),
    ],
)

WORD_COUNT = Snippet(
    level="Beginner",
    complexity="O(n) time, O(n) space",
    title="Top words in a sentence",
    language="Python",
    overview="Splits text into words, strips punctuation, and uses collections.Counter to "
             "count how often each word appears, then returns the most common ones.",
    code='''from collections import Counter


def top_words(text, n=3):
    words = text.lower().split()
    cleaned = [w.strip(".,!?;:") for w in words]
    counts = Counter(w for w in cleaned if w)
    return counts.most_common(n)


sample = "The cat sat. The cat ran! A dog sat too."
for word, count in top_words(sample):
    print(f"{word}: {count}")''',
    sections=[
        Section(1, 1, "Import Counter",
                "`Counter` is a dictionary subclass from the standard library that counts "
                "how many times each item appears.", ["imports", "standard library"]),
        Section(4, 4, "Function with a default",
                "`n=3` is a default argument: callers can leave it out and get the top 3.",
                ["default arguments"]),
        Section(5, 5, "Split into words",
                "`lower()` makes \"The\" and \"the\" the same word, and `split()` breaks the "
                "text on whitespace into a list.", ["string methods"]),
        Section(6, 6, "Strip punctuation",
                "A list comprehension builds a new list; `strip(\".,!?;:\")` removes those "
                "characters from both ends of each word.", ["list comprehension"]),
        Section(7, 7, "Count the words",
                "A generator expression feeds every non-empty word into `Counter`, which "
                "tallies them.", ["generator expression", "Counter"]),
        Section(8, 8, "Most common first",
                "`most_common(n)` returns a list of `(word, count)` pairs, highest counts first.",
                ["tuples"]),
        Section(11, 13, "Use it",
                "The `for` loop unpacks each pair into `word` and `count`, and the f-string "
                "inserts them into the printed text.", ["tuple unpacking", "f-strings"]),
    ],
)

STACK = Snippet(
    level="Intermediate",
    complexity="O(n) time, O(n) space",
    title="Stack + balanced brackets",
    language="Python",
    overview="A small Stack class (last in, first out) and a classic use for it: checking "
             "that every bracket in an expression is closed in the right order.",
    code='''class Stack:
    def __init__(self):
        self._items = []

    def push(self, item):
        self._items.append(item)

    def pop(self):
        if self.is_empty():
            raise IndexError("pop from empty stack")
        return self._items.pop()

    def peek(self):
        return self._items[-1] if self._items else None

    def is_empty(self):
        return len(self._items) == 0


def is_balanced(expr):
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = Stack()
    for ch in expr:
        if ch in "([{":
            stack.push(ch)
        elif ch in pairs:
            if stack.is_empty() or stack.pop() != pairs[ch]:
                return False
    return stack.is_empty()


print(is_balanced("{[()()]}"))
print(is_balanced("([)]"))''',
    sections=[
        Section(1, 3, "Class and constructor",
                "`__init__` runs when a Stack is created and gives it an empty list. The "
                "leading underscore in `_items` signals \"internal, don't touch\".",
                ["classes", "constructor"]),
        Section(5, 6, "push",
                "Adds an item to the top of the stack, which is the end of the list.",
                ["methods"]),
        Section(8, 11, "pop with a guard",
                "Removing from an empty stack is a bug, so raise a clear `IndexError` first. "
                "Otherwise `list.pop()` removes and returns the last item.", ["exceptions"]),
        Section(13, 14, "peek",
                "Looks at the top item without removing it. The conditional expression "
                "returns None when the stack is empty.", ["conditional expression"]),
        Section(16, 17, "is_empty",
                "True when the list has no items.", ["booleans"]),
        Section(20, 22, "Set up the checker",
                "`pairs` maps each closing bracket to its opening partner, and we start "
                "with an empty stack.", ["dictionaries"]),
        Section(23, 25, "Remember openers",
                "Walk through every character, pushing opening brackets so we know which "
                "closer we expect next.", ["for loop", "membership test"]),
        Section(26, 28, "Match closers",
                "A closer must match the most recent opener. If the stack is empty or the "
                "popped opener is the wrong kind, the expression is unbalanced.",
                ["short-circuit or"]),
        Section(29, 29, "Nothing left open",
                "If any opener is still on the stack, something was never closed.", []),
        Section(32, 33, "Test it",
                "The first expression is balanced (True); the second closes `(` with `]` (False).",
                ["testing"]),
    ],
)

FIZZBUZZ = Snippet(
    level="Beginner",
    title="FizzBuzz",
    language="Python",
    overview="Prints the numbers 1 to 15, but multiples of 3 become Fizz, multiples of 5 "
             "become Buzz, and multiples of both become FizzBuzz. A classic first exercise "
             "in loops and conditions.",
    complexity="O(n) time, O(1) space",
    code='''for n in range(1, 16):
    if n % 15 == 0:
        print("FizzBuzz")
    elif n % 3 == 0:
        print("Fizz")
    elif n % 5 == 0:
        print("Buzz")
    else:
        print(n)''',
    sections=[
        Section(1, 1, "Loop over 1 to 15",
                "`range(1, 16)` produces 1, 2, ... 15; the end number is not included.",
                ["for loop", "range"]),
        Section(2, 3, "Both 3 and 5",
                "`%` gives the remainder, so `n % 15 == 0` means n divides by 15. This check "
                "must come first, or Fizz would win for 15.", ["modulo", "order of checks"]),
        Section(4, 7, "Fizz or Buzz",
                "`elif` is only checked when the earlier conditions were false.", ["elif"]),
        Section(8, 9, "Otherwise the number",
                "`else` catches everything that matched nothing above.", ["else"]),
    ],
)

FIBONACCI = Snippet(
    level="Intermediate",
    title="Fibonacci with memoization",
    language="Python",
    overview="Plain recursive Fibonacci recomputes the same values again and again. Caching "
             "each result with lru_cache turns it from exponential time into linear time.",
    complexity="O(n) time, O(n) space",
    code='''from functools import lru_cache


@lru_cache(maxsize=None)
def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


for i in range(10):
    print(i, fib(i))
print(fib(80))''',
    sections=[
        Section(1, 1, "Import the cache",
                "`lru_cache` is a decorator from the standard library that remembers a "
                "function's results.", ["imports"]),
        Section(4, 4, "Decorate the function",
                "`@` applies the decorator. `maxsize=None` means it never forgets a result.",
                ["decorators", "memoization"]),
        Section(5, 5, "Signature", "`fib(n)` returns the n-th Fibonacci number.", ["functions"]),
        Section(6, 7, "Base case",
                "fib(0) is 0 and fib(1) is 1. Every recursion needs a case that stops it.",
                ["base case"]),
        Section(8, 8, "Recursive case",
                "Each number is the sum of the two before it. Thanks to the cache, each "
                "fib(k) is only computed once.", ["recursion"]),
        Section(11, 13, "Try it",
                "Prints the first ten numbers, then fib(80), which would take years without "
                "the cache.", ["testing"]),
    ],
)

LIST_BASICS = Snippet(
    level="Beginner",
    title="Filter and transform a list",
    language="Python",
    overview="Processes a list of test scores: keep the passing ones, add a bonus, then "
             "total them to find the average. Shows list comprehensions and built-ins like "
             "sum, min and len.",
    complexity="O(n) time, O(n) space",
    code='''scores = [72, 95, 58, 88, 64, 100]

passed = [s for s in scores if s >= 65]
curved = [min(s + 5, 100) for s in passed]
total = sum(curved)
average = total / len(curved)

print("passed:", passed)
print("curved:", curved)
print(f"average: {average:.1f}")''',
    sections=[
        Section(1, 1, "The data",
                "A list in square brackets holds six scores.", ["lists"]),
        Section(3, 3, "Keep the passing scores",
                "A list comprehension with an `if` keeps only the items where the condition "
                "is true, like a filter.", ["list comprehension", "filtering"]),
        Section(4, 4, "Add a bonus",
                "Another comprehension transforms every item. `min(s + 5, 100)` caps the "
                "bonus so no score goes above 100.", ["transforming", "min"]),
        Section(5, 5, "Total",
                "`sum` adds up every number in the list.", ["sum"]),
        Section(6, 6, "Average",
                "`len` counts the items; dividing with `/` always gives a float.", ["len"]),
        Section(8, 10, "Print the results",
                "`print` separates its arguments with spaces. In the f-string, `:.1f` rounds "
                "the average to one decimal place.", ["f-strings", "formatting"]),
    ],
)

RETRY = Snippet(
    level="Advanced",
    title="Retry decorator",
    language="Python",
    overview="A decorator that re-runs a function when it raises an error, waiting between "
             "attempts. This is how real programs survive flaky things like network calls. "
             "It combines closures, *args/**kwargs and exception handling.",
    complexity="O(times) attempts",
    code='''import functools
import time


def retry(times=3, delay=0.1):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, times + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as error:
                    print(f"attempt {attempt} failed: {error}")
                    if attempt == times:
                        raise
                    time.sleep(delay)
        return wrapper
    return decorator


calls = {"count": 0}


@retry(times=5)
def flaky():
    calls["count"] += 1
    if calls["count"] < 3:
        raise ConnectionError("network blip")
    return "ok"


print(flaky())''',
    sections=[
        Section(1, 2, "Imports",
                "`functools` has helpers for writing decorators, and `time` lets us pause.",
                ["imports"]),
        Section(5, 5, "Decorator with settings",
                "`retry(times, delay)` takes settings and returns the real decorator. That's "
                "why it's used as `@retry(times=5)` with brackets.", ["decorator factory"]),
        Section(6, 8, "Wrap the function",
                "`decorator` receives the original function and builds `wrapper` around it. "
                "`*args, **kwargs` accept any arguments, and `functools.wraps` keeps the "
                "original name and docstring.", ["closures", "*args/**kwargs"]),
        Section(9, 11, "Try each attempt",
                "Loop up to `times` attempts. If the call succeeds, `return` hands back its "
                "result and ends the loop.", ["try/except"]),
        Section(12, 16, "Handle a failure",
                "Report the error. On the last attempt, a bare `raise` re-raises the same "
                "error to the caller; otherwise wait and try again.", ["exceptions", "re-raise"]),
        Section(17, 18, "Return the layers",
                "Each layer returns the next one inward: `retry` returns `decorator`, which "
                "returns `wrapper`.", ["higher-order functions"]),
        Section(21, 21, "A call counter",
                "A dictionary the function can update, so we can fail on purpose at first.",
                ["mutable state"]),
        Section(24, 29, "A flaky function",
                "Fails with `ConnectionError` on the first two calls, then succeeds. The "
                "decorator line wraps it in the retry logic.", ["decorators"]),
        Section(32, 32, "Run it",
                "Prints two failed attempts, then `ok`.", ["testing"]),
    ],
)

LEVELS = {"Beginner": 0, "Intermediate": 1, "Advanced": 2}
TUTORIALS = sorted([FIZZBUZZ, WORD_COUNT, LIST_BASICS, BINARY_SEARCH, FIBONACCI, STACK,
                    RETRY], key=lambda t: LEVELS[t.level])
