#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
以太坊兼容链代币余额查询工具
支持查询原生代币（ETH/BNB/MATIC等）和ERC20代币余额
"""
import json
import sys
from typing import Optional, Dict, Any
from decimal import Decimal

import requests


class EthTokenBalanceChecker:
    """以太坊兼容链代币余额查询器"""

    # 预定义的RPC端点
    RPC_ENDPOINTS = {
        'ethereum': 'https://eth.llamarpc.com',
        'eth': 'https://eth.llamarpc.com',
        'bsc': 'https://bsc-dataseed.binance.org',
        'binance': 'https://bsc-dataseed.binance.org',
        'polygon': 'https://polygon-rpc.com',
        'matic': 'https://polygon-rpc.com',
        'arbitrum': 'https://arb1.arbitrum.io/rpc',
        'arb': 'https://arb1.arbitrum.io/rpc',
        'optimism': 'https://mainnet.optimism.io',
        'op': 'https://mainnet.optimism.io',
        'base': 'https://mainnet.base.org',
        'avalanche': 'https://api.avax.network/ext/bc/C/rpc',
        'avax': 'https://api.avax.network/ext/bc/C/rpc',
        'plasma': 'https://rpc.plasma.to'
    }

    # ERC20 balanceOf 方法签名
    BALANCE_OF_SIGNATURE = '0x70a08231'

    def __init__(self, rpc_url: str, timeout: int = 30):
        """
        初始化
        :param rpc_url: RPC端点URL或链名称（如'ethereum', 'bsc'等）
        :param timeout: 请求超时时间（秒）
        """
        if rpc_url.lower() in self.RPC_ENDPOINTS:
            self.rpc_url = self.RPC_ENDPOINTS[rpc_url.lower()]
            self.chain_name = rpc_url.lower()
        else:
            self.rpc_url = rpc_url
            self.chain_name = 'custom'
        self.timeout = timeout
        self.request_id = 1

    def _make_rpc_call(self, method: str, params: list) -> Dict[str, Any]:
        """
        发送JSON-RPC请求
        :param method: RPC方法名
        :param params: 方法参数
        :return: RPC响应结果
        """
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self.request_id
        }
        self.request_id += 1

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; EthBalanceChecker/1.0)"
        }

        response = requests.post(
            self.rpc_url,
            json=payload,
            headers=headers,
            timeout=self.timeout
        )
        response.raise_for_status()

        result = response.json()
        if 'error' in result:
            raise Exception(f"RPC Error: {result['error']}")

        return result.get('result')

    def get_native_balance(self, address: str, block: str = 'latest') -> Decimal:
        """
        获取原生代币余额（ETH/BNB/MATIC等）
        :param address: 钱包地址
        :param block: 区块高度，默认'latest'
        :return: 余额（单位：ether）
        """
        if not address.startswith('0x'):
            address = '0x' + address

        balance_wei = self._make_rpc_call('eth_getBalance', [address, block])
        balance_wei_int = int(balance_wei, 16)
        balance_ether = Decimal(balance_wei_int) / Decimal(10 ** 18)

        return balance_ether

    def get_token_balance(self, address: str, token_address: str,
                         decimals: int = 18, block: str = 'latest') -> Decimal:
        """
        获取ERC20代币余额
        :param address: 钱包地址
        :param token_address: 代币合约地址
        :param decimals: 代币精度，默认18
        :param block: 区块高度，默认'latest'
        :return: 代币余额
        """
        if not address.startswith('0x'):
            address = '0x' + address
        if not token_address.startswith('0x'):
            token_address = '0x' + token_address

        # 构造balanceOf(address)调用数据
        # 方法签名: 0x70a08231
        # 参数: 地址（补齐到32字节）
        address_param = address[2:].lower().zfill(64)
        data = self.BALANCE_OF_SIGNATURE + address_param

        # 调用合约
        result = self._make_rpc_call('eth_call', [
            {
                'to': token_address,
                'data': data
            },
            block
        ])

        if result is None or result == '0x':
            return Decimal(0)

        balance_raw = int(result, 16)
        balance = Decimal(balance_raw) / Decimal(10 ** decimals)

        return balance

    def get_token_decimals(self, token_address: str) -> int:
        """
        获取ERC20代币精度
        :param token_address: 代币合约地址
        :return: 代币精度
        """
        if not token_address.startswith('0x'):
            token_address = '0x' + token_address

        # decimals() 方法签名: 0x313ce567
        data = '0x313ce567'

        result = self._make_rpc_call('eth_call', [
            {
                'to': token_address,
                'data': data
            },
            'latest'
        ])

        if result is None or result == '0x':
            return 18  # 默认精度

        return int(result, 16)

    def get_token_symbol(self, token_address: str) -> str:
        """
        获取ERC20代币符号
        :param token_address: 代币合约地址
        :return: 代币符号
        """
        if not token_address.startswith('0x'):
            token_address = '0x' + token_address

        # symbol() 方法签名: 0x95d89b41
        data = '0x95d89b41'

        try:
            result = self._make_rpc_call('eth_call', [
                {
                    'to': token_address,
                    'data': data
                },
                'latest'
            ])

            if result and result != '0x':
                # 解析返回的字符串
                result_bytes = bytes.fromhex(result[2:])
                # 跳过前64字节（偏移量和长度信息）
                if len(result_bytes) >= 64:
                    length = int.from_bytes(result_bytes[32:64], 'big')
                    symbol = result_bytes[64:64+length].decode('utf-8', errors='ignore')
                    return symbol
        except Exception:
            pass

        return 'UNKNOWN'

    def get_all_info(self, address: str, token_address: Optional[str] = None) -> Dict[str, Any]:
        """
        获取完整的余额信息
        :param address: 钱包地址
        :param token_address: 代币合约地址（可选，不提供则只查询原生代币）
        :return: 包含余额信息的字典
        """
        info = {
            'address': address,
            'chain': self.chain_name,
            'rpc_url': self.rpc_url,
            'native_balance': None,
            'token_balance': None,
            'token_info': None
        }

        # 查询原生代币余额
        try:
            native_balance = self.get_native_balance(address)
            info['native_balance'] = str(native_balance)
        except Exception as e:
            info['native_balance_error'] = str(e)

        # 查询ERC20代币余额
        if token_address:
            try:
                decimals = self.get_token_decimals(token_address)
                symbol = self.get_token_symbol(token_address)
                balance = self.get_token_balance(address, token_address, decimals)

                info['token_info'] = {
                    'address': token_address,
                    'symbol': symbol,
                    'decimals': decimals
                }
                info['token_balance'] = str(balance)
            except Exception as e:
                info['token_balance_error'] = str(e)

        return info


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description='查询以太坊兼容链上特定地址的代币余额',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 查询以太坊主网上的ETH余额
  python eth_token_balance.py -c ethereum -a <wallet-address>

  # 查询BSC上的BNB和代币余额
  python eth_token_balance.py -c bsc -a <wallet-address> -t <token-address>

  # 使用自定义RPC
  python eth_token_balance.py -r https://your-rpc-url.com -a 0x...

支持的链:
  ethereum/eth, bsc/binance, polygon/matic, arbitrum/arb,
  optimism/op, base, avalanche/avax, plasma/plasm
        """
    )

    parser.add_argument('-c', '--chain', type=str,
                       help='链名称 (ethereum, bsc, polygon等)')
    parser.add_argument('-r', '--rpc', type=str,
                       help='自定义RPC URL')
    parser.add_argument('-a', '--address', type=str, required=True,
                       help='要查询的钱包地址')
    parser.add_argument('-t', '--token', type=str,
                       help='ERC20代币合约地址（可选）')
    parser.add_argument('--timeout', type=int, default=30,
                       help='请求超时时间（秒），默认30')
    parser.add_argument('-j', '--json', action='store_true',
                       help='以JSON格式输出')

    args = parser.parse_args()

    # 确定RPC URL
    if args.rpc:
        rpc_url = args.rpc
    elif args.chain:
        rpc_url = args.chain
    else:
        parser.error('必须指定 --chain 或 --rpc')

    try:
        checker = EthTokenBalanceChecker(rpc_url, timeout=args.timeout)
        info = checker.get_all_info(args.address, args.token)

        if args.json:
            print(json.dumps(info, indent=2, ensure_ascii=False))
        else:
            print(f"链: {info['chain']}")
            print(f"地址: {info['address']}")
            print(f"RPC: {info['rpc_url']}")
            print()

            if 'native_balance' in info and info['native_balance'] is not None:
                print(f"原生代币余额: {info['native_balance']}")
            if 'native_balance_error' in info:
                print(f"原生代币查询错误: {info['native_balance_error']}")

            if info.get('token_info'):
                print()
                print("代币信息:")
                print(f"  合约地址: {info['token_info']['address']}")
                print(f"  符号: {info['token_info']['symbol']}")
                print(f"  精度: {info['token_info']['decimals']}")
                print(f"  余额: {info['token_balance']}")
            if 'token_balance_error' in info:
                print(f"代币查询错误: {info['token_balance_error']}")

        return 0

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
