def find_closest_fib_position(num):
    if num <= 1:
        return 1

    a, b = 1, 1
    position = 2  # 初始化为第二个数的位置

    while b < num:
        a, b = b, a + b
        position += 1

    # 检查距离最近的两个斐波那契数，选取距离更近的那个
    if abs(b - num) < abs(a - num):
        return position
    else:
        return position - 1
