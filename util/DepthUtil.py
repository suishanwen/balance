def merge_order_book(full_data, update_data):
    # 解析增量数据
    asks_update = update_data['asks']
    bids_update = update_data['bids']

    # 解析全量数据
    asks_full = full_data['asks']
    bids_full = full_data['bids']

    # 更新asks数据
    for update in asks_update:
        price = update[0]
        size = update[1]

        # 查找相同价格的深度数据
        found = False
        for i, ask in enumerate(asks_full):
            if ask[0] == price:
                found = True
                if size == 0:
                    # 如果数量为0，删除该深度信息
                    asks_full.pop(i)
                else:
                    # 数量有变化，替换深度信息
                    asks_full[i] = update
                break

        if not found and size != 0:
            # 没有找到相同价格，插入并排序
            asks_full.append(update)
            asks_full = sorted(asks_full, key=lambda x: float(x[0]))

    # 更新bids数据
    for update in bids_update:
        price = update[0]
        size = update[1]

        # 查找相同价格的深度数据
        found = False
        for i, bid in enumerate(bids_full):
            if bid[0] == price:
                found = True
                if size == 0:
                    # 如果数量为0，删除该深度信息
                    bids_full.pop(i)
                else:
                    # 数量有变化，替换深度信息
                    bids_full[i] = update
                break

        if not found and size != 0:
            # 没有找到相同价格，插入并排序
            bids_full.append(update)
            bids_full = sorted(bids_full, key=lambda x: float(x[0]), reverse=True)

    return {
        "asks": asks_full,
        "bids": bids_full
    }
