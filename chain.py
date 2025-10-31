import json
import os
from typing import List
from network import list_peers
import socket
from block import Block, create_block, create_block_from_dict, create_genesis_block
from network import broadcast_block, broadcast_transaction


def load_chain(fpath: str) -> List[Block]:
    if os.path.exists(fpath):
        with open(fpath) as f:
            data = json.load(f)
            blockchain = []
            for block_data in data:
                block = create_block_from_dict(block_data)
                blockchain.append(block)
            return blockchain

    return [create_genesis_block()]


def save_chain(fpath: str, chain: list[Block]):
    blockchain_serializable = []
    for b in chain:
        blockchain_serializable.append(b.as_dict())

    with open(fpath, "w") as f:
        json.dump(blockchain_serializable, f, indent=2)


def valid_chain(chain: List[Block]):
    """
    Determina se uma dada blockchain é válida
    :param chain: A blockchain
    :return: True se for válida, False se não for
    """
    last_block = chain[0]
    current_index = 1

    while current_index < len(chain):
        block = chain[current_index]
        # Verifica se o hash do bloco anterior está correto
        if block.prev_hash != last_block.hash:
            print("[!] Erro de validacao: O hash anterior nao bate.")
            return False

        # Verifica se o índice está sequencial
        if block.index != current_index:
            print(f"[!] Erro de validacao: Indice do bloco {block.index} fora de ordem.")
            return False
        
        # Recalcula o hash do bloco para garantir que não foi adulterado
        # if hash_block(block) != block.hash:
        #    return False

        last_block = block
        current_index += 1

    return True


def print_chain(blockchain: List[Block]):
    for b in blockchain:
        print(f"Index: {b.index}, Hash: {b.hash[:10]}..., Tx: {len(b.transactions)}")


def mine_block(
    transactions: List,
    blockchain: List[Block],
    node_id: str,
    reward: int,
    difficulty: int,
    blockchain_fpath: str,
    peers_fpath: str,
    port: int,
):
    new_block = create_block(
        transactions,
        blockchain[-1].hash,
        miner=node_id,
        index=len(blockchain),
        reward=reward,
        difficulty=difficulty,
    )
    blockchain.append(new_block)
    transactions.clear()
    save_chain(blockchain_fpath, blockchain)
    broadcast_block(new_block, peers_fpath, port)
    print(f"[✓] Block {new_block.index} mined and broadcasted.")


def make_transaction(sender, recipient, amount, transactions, peers_file, port):
    tx = {"from": sender, "to": recipient, "amount": amount}
    transactions.append(tx)
    broadcast_transaction(tx, peers_file, port)
    print("[+] Transaction added.")


def get_balance(node_id: str, blockchain: List[Block]) -> float:
    balance = 0
    for block in blockchain:
        for tx in block.transactions:
            if tx["to"] == node_id:
                balance += float(tx["amount"])
            if tx["from"] == node_id:
                balance -= float(tx["amount"])
    return balance


def on_valid_block_callback(fpath, chain):
    save_chain(fpath, chain)


def resolve_conflicts(peers_fpath: str, port: int, blockchain: List[Block]):
    """
    Este é o nosso algoritmo de consenso, ele resolve conflitos
    substituindo nossa cadeia pela mais longa e válida na rede.
    """
    neighbours = list_peers(peers_fpath)
    longest_valid_chain = None
    max_length = 0

    # Passo 1: Considera a própria cadeia como uma candidata APENAS SE for válida
    if valid_chain(blockchain):
        longest_valid_chain = blockchain
        max_length = len(blockchain)

    # Passo 2: Pega e verifica as cadeias de todos os nós da rede
    for node_ip in neighbours:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((node_ip, port))
            s.send(json.dumps({"type": "get_chain"}).encode())
            
            response = s.recv(8192).decode()
            if not response:
                continue

            data = json.loads(response)
            length = data['length']
            chain_data = data['chain']
            
            peer_chain = [create_block_from_dict(b) for b in chain_data]

            # Se a cadeia do vizinho for mais longa que a maior válida até agora E for válida,
            # ela se torna a nova melhor cadeia.
            if length > max_length and valid_chain(peer_chain):
                max_length = length
                longest_valid_chain = peer_chain

        except Exception as e:
            print(f"[!] Nao foi possivel conectar ao par {node_ip}: {e}")
            continue

    # Passo 3: Se não encontramos nenhuma cadeia válida, não fazemos nada
    if longest_valid_chain is None:
        print("[!] Nenhuma cadeia valida foi encontrada na rede. Mantendo a local por seguranca.")
        return blockchain

    # Passo 4: Se a melhor cadeia encontrada for diferente da nossa, substituímos.
    if longest_valid_chain is not blockchain:
        print("[i] Cadeia local substituida pela melhor cadeia encontrada na rede.")
        return longest_valid_chain
    else:
        print("[i] A cadeia local ja e a melhor e autoritativa.")
        return blockchain
