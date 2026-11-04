calm = sorted(set(range(128)) - set(map(int, open("/opt/mvtrx/skip_books.txt").read().split())))
sl = calm[2::5]                                  # every fifth calm book: a fixed rule, not picked on results
x1b = set(map(int, open("/opt/mvtrx/skip_x2.txt").read().split()))   # x2 already skips the x1 books
open("/opt/mvtrx/sleeve_books_x2.txt", "w").write(" ".join(map(str, sl)))
open("/opt/mvtrx/skip_x2.txt", "w").write(" ".join(map(str, sorted(x1b | set(sl)))))
x1q = set(range(128)) - set(map(int, open("/opt/mvtrx/skip_x1.txt").read().split()))
print("x2 sleeve books:", sl, "| overlap with x1 quoted books:", len(set(sl) & x1q), "| x2 now quotes", 128 - len(x1b | set(sl)), "books")
