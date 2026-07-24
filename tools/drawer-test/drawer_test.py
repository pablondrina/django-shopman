#!/usr/bin/env python3
"""
drawer_test.py — teste físico de gaveta de dinheiro + impressora térmica (ESC/POS).

Ferramenta STANDALONE (stdlib apenas, sem Django, sem rede com o staging) para
validar a cadeia física na loja durante o staging: impressora térmica responde?
a gaveta abre no pulso? o corte funciona? Rode no computador da loja, na mesma
rede (ou USB) da impressora.

A gaveta de dinheiro não fala com computador: ela é acionada pela IMPRESSORA
via pulso no conector RJ11/RJ12 ("kick"). O comando ESC/POS é `ESC p m t1 t2`.
Se este script abre a gaveta, o hardware está pronto para a Fase C (integração
de impressão do PDV) — o que faltará é só o software do agente local.

Modos de conexão (escolha um):

  1. Rede (impressora com Ethernet/Wi-Fi, porta RAW 9100 — padrão Epson/Bematech/Elgin):
       python3 drawer_test.py --network 192.168.0.50
       python3 drawer_test.py --network 192.168.0.50:9100 --receipt

  2. CUPS (impressora instalada no macOS/Linux; envia em modo raw):
       lpstat -p                       # descobre o nome da fila
       python3 drawer_test.py --cups NOME_DA_FILA --receipt

  3. Dispositivo direto (Linux, USB):
       python3 drawer_test.py --device /dev/usb/lp0

Opções:
  --kick-only          só o pulso da gaveta (sem imprimir nada)
  --receipt            imprime um cupom de teste (e abre a gaveta)
  --pin {2,5}          pino do conector da gaveta (padrão 2; use 5 se não abrir)
  --no-cut             não aciona a guilhotina após o cupom

Diagnóstico rápido:
  - Nada acontece na rede → confira IP (imprima a página de auto-teste da
    impressora segurando o botão FEED ao ligar) e se a porta 9100 está aberta.
  - Cupom sai mas gaveta não abre → teste `--pin 5`; confira o cabo RJ11 na
    porta "DK" da impressora (não é a porta de rede!).
  - CUPS imprime lixo → a fila não está em modo raw; prefira o modo --network.
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import tempfile
from datetime import datetime

ESC = b"\x1b"
GS = b"\x1d"


def kick_pulse(pin: int) -> bytes:
    """ESC p m t1 t2 — pulso de ~50ms/500ms no pino da gaveta."""
    m = b"\x00" if pin == 2 else b"\x01"
    return ESC + b"p" + m + b"\x19\xfa"


def test_receipt() -> bytes:
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    lines = [
        ESC + b"@",                          # init
        ESC + b"a\x01",                      # center
        ESC + b"E\x01" + b"NELSON BOULANGERIE\n" + ESC + b"E\x00",
        b"Teste de impressora + gaveta\n",
        ("%s\n" % now).encode("cp850", "replace"),
        b"------------------------------\n",
        ESC + b"a\x00",                      # left
        b"1x Croissant Tradicional\n",
        b"1x Pain au Chocolat\n",
        b"1x Madeleine\n",
        b"------------------------------\n",
        ESC + b"a\x01",
        b"Se a gaveta abriu: hardware OK!\n",
        b"Fase C liga isso ao PDV.\n\n\n",
    ]
    return b"".join(lines)


def build_payload(args: argparse.Namespace) -> bytes:
    payload = ESC + b"@"
    if args.receipt:
        payload += test_receipt()
    payload += kick_pulse(args.pin)
    if args.receipt and not args.no_cut:
        payload += GS + b"V\x42\x00"          # partial cut com feed
    return payload


def send_network(target: str, payload: bytes) -> None:
    host, _, port_s = target.partition(":")
    port = int(port_s or "9100")
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.sendall(payload)
    print(f"OK: {len(payload)} bytes enviados para {host}:{port}")


def send_cups(queue: str, payload: bytes) -> None:
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as fh:
        fh.write(payload)
        path = fh.name
    result = subprocess.run(
        ["lp", "-d", queue, "-o", "raw", path], capture_output=True, text=True
    )
    if result.returncode != 0:
        sys.exit(f"ERRO no lp: {result.stderr.strip()}")
    print(f"OK: job enviado à fila '{queue}' em modo raw ({result.stdout.strip()})")


def send_device(device: str, payload: bytes) -> None:
    with open(device, "wb") as fh:
        fh.write(payload)
    print(f"OK: {len(payload)} bytes escritos em {device}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 2)[1])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--network", metavar="HOST[:PORT]", help="impressora de rede (RAW 9100)")
    target.add_argument("--cups", metavar="FILA", help="fila CUPS instalada (modo raw)")
    target.add_argument("--device", metavar="CAMINHO", help="dispositivo direto (ex.: /dev/usb/lp0)")
    parser.add_argument("--kick-only", action="store_true", help="só o pulso da gaveta")
    parser.add_argument("--receipt", action="store_true", help="imprime cupom de teste")
    parser.add_argument("--pin", type=int, choices=(2, 5), default=2, help="pino da gaveta (padrão 2)")
    parser.add_argument("--no-cut", action="store_true", help="não corta o papel")
    args = parser.parse_args()

    if not args.receipt:
        args.kick_only = True

    payload = build_payload(args)
    if args.network:
        send_network(args.network, payload)
    elif args.cups:
        send_cups(args.cups, payload)
    else:
        send_device(args.device, payload)

    print("Gaveta abriu? Se não: tente --pin 5 e confira o RJ11 na porta DK da impressora.")


if __name__ == "__main__":
    main()
