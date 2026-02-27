# Auto-generated skills by Neko

# 来源任务: 帮我生成斐波那契数列前10位
def calculate_fibonacci(n=10):
    """
    生成前 n 位斐波那契数列。
    参数: n (int) - 需要生成的数字个数
    """
    if n <= 0: return []
    if n == 1: return [0]
    fib_sequence = [0, 1]
    while len(fib_sequence) < n:
        fib_sequence.append(fib_sequence[-1] + fib_sequence[-2])
    return fib_sequence

