<script setup lang="ts">
// Receipt (spec §D3 · web/CSS print) — a thermal-style (80mm) layout printed via
// the browser's print path (kiosk window.print). It renders a frozen finalize
// snapshot through `presentation/receipt` (pure shaping). On screen it is hidden;
// it only becomes visible inside @media print (see the print rules in
// assets/css/tailwind.css). Real-hardware transport (ESC-POS / network ePOS) is
// validated on a device — this is the web prototype.
import type { POSPaymentMethodProjection } from "~/types/pos";
import type { PosReceiptSnapshot } from "~/presentation/receipt";
import { receiptLines, receiptPayments } from "~/presentation/receipt";

const props = defineProps<{
  receipt: PosReceiptSnapshot;
  terminalLabel: string;
  paymentMethods: POSPaymentMethodProjection[];
}>();

const lines = computed(() => receiptLines(props.receipt));
const payments = computed(() => receiptPayments(props.receipt, props.paymentMethods));
const printedAt = computed(() => new Date(props.receipt.printedAtMs).toLocaleString("pt-BR"));
</script>

<template>
  <div class="mx-auto w-[80mm] max-w-full bg-white px-3 py-4 font-mono text-[12px] leading-snug text-black">
    <div class="text-center">
      <p class="text-sm font-bold uppercase tracking-wide">{{ terminalLabel }}</p>
      <p class="text-[11px]">Recibo não fiscal</p>
    </div>
    <hr class="my-2 border-t border-dashed border-black/40" />
    <div class="flex justify-between"><span>Pedido</span><span class="font-semibold">{{ receipt.orderRef }}</span></div>
    <div v-if="receipt.tabDisplay" class="flex justify-between"><span>Comanda</span><span>#{{ receipt.tabDisplay }}</span></div>
    <div class="flex justify-between"><span>Data</span><span>{{ printedAt }}</span></div>
    <div v-if="receipt.customerName" class="flex justify-between"><span>Cliente</span><span>{{ receipt.customerName }}</span></div>
    <div class="flex justify-between"><span>Entrega</span><span>{{ receipt.fulfillmentLabel }}</span></div>
    <hr class="my-2 border-t border-dashed border-black/40" />
    <table class="w-full">
      <tbody>
        <tr v-for="(line, idx) in lines" :key="idx" class="align-top">
          <td class="pr-1 tabular-nums">{{ line.qty }}×</td>
          <td class="w-full">
            {{ line.name }}
            <span v-if="line.discountPct" class="block text-[10px]">desconto −{{ line.discountPct }}%</span>
          </td>
          <td class="whitespace-nowrap pl-1 text-right tabular-nums">{{ line.totalDisplay }}</td>
        </tr>
      </tbody>
    </table>
    <hr class="my-2 border-t border-dashed border-black/40" />
    <div class="flex justify-between text-sm font-bold">
      <span>Total</span><span class="tabular-nums">{{ receipt.totalDisplay }}</span>
    </div>
    <div v-for="(payment, idx) in payments" :key="idx" class="flex justify-between text-[11px]">
      <span>{{ payment.label }}</span><span class="tabular-nums">{{ payment.amountDisplay }}</span>
    </div>
    <hr class="my-2 border-t border-dashed border-black/40" />
    <p class="text-center text-[11px]">Obrigado pela preferência!</p>
  </div>
</template>
