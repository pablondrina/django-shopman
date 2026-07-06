// Flat config do KDS: preset do Nuxt (@nuxt/eslint gera .nuxt/eslint.config.mjs no
// `nuxt prepare`) + base compartilhada do operator-kit + Prettier por último.
import withNuxt from "./.nuxt/eslint.config.mjs";
import operatorKit from "../operator-kit/eslint.config.base.mjs";
import prettier from "eslint-config-prettier";

export default withNuxt(...operatorKit, prettier);
