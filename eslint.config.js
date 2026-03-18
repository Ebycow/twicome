import globals from "globals";
import jsdoc from "eslint-plugin-jsdoc";

export default [
  {
    files: ["app/static/js/**/*.js"],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: "script",
      globals: {
        ...globals.browser,
      },
    },
    plugins: {
      jsdoc,
    },
    rules: {
      // ── JSDoc ──────────────────────────────────────────────────────────────

      // 名前付き関数宣言に JSDoc を必須（コールバック・無名関数は除外）
      "jsdoc/require-jsdoc": ["error", {
        "require": {
          "FunctionDeclaration": true,
          "FunctionExpression": false,
          "ArrowFunctionExpression": false,
        },
      }],
      // @param タグの記述を必須
      "jsdoc/require-param": "error",
      // @param の説明文を必須
      "jsdoc/require-param-description": "error",
      // @param 名と実引数名の一致を検証
      "jsdoc/check-param-names": "error",
      // 戻り値がある関数に @returns を必須（void は除外）
      "jsdoc/require-returns": ["error", { "checkGetters": false }],
      // @returns の説明文を必須
      "jsdoc/require-returns-description": "error",

      // ── スコープ・宣言 ─────────────────────────────────────────────────────

      // var → const/let への移行（関数スコープより読みやすいブロックスコープ）
      "no-var": "error",
      // 再代入しない変数は const（変更される変数を let で明示）
      "prefer-const": "error",
      // 未使用の変数を検出（catch 引数・関数引数は除外）
      "no-unused-vars": ["error", { "args": "none", "caughtErrors": "none" }],

      // ── 等価・型変換 ───────────────────────────────────────────────────────

      // === を使う（null との比較のみ == を許容）
      "eqeqeq": ["error", "always", { "null": "ignore" }],
      // !! や +x のような暗黙的な型変換を禁止（Boolean(x) / Number(x) を使う）
      // 記号だけで型変換の意図が伝わりにくい箇所を明示化する
      "no-implicit-coercion": ["error", { "boolean": true, "number": true, "string": false }],

      // ── 文字列 ─────────────────────────────────────────────────────────────

      // 'Hello ' + name + '!' → `Hello ${name}!`（構造が一目でわかる）
      "prefer-template": "error",

      // ── 制御フローの平坦化 ─────────────────────────────────────────────────

      // if/for/while のブレース省略を禁止（読み間違い防止）
      "curly": ["error", "all"],
      // return 後の else を除去（不要なネストを減らして構造を平坦に）
      "no-else-return": "error",
      // else { if (...) } → else if (...)（構造的に同じなので短い形を強制）
      "no-lonely-if": "error",
      // ネストした三項演算子を禁止（a ? b ? c : d : e は解析が困難）
      "no-nested-ternary": "error",

      // ── オブジェクト ────────────────────────────────────────────────────────

      // { fn: fn, x: x } → { fn, x }（繰り返しが消えて構造が見やすい）
      "object-shorthand": ["error", "always"],
      // obj['key'] → obj.key（識別子として有効なキーはドット記法を使う）
      "dot-notation": "error",

      // ── その他 ─────────────────────────────────────────────────────────────

      // 変数名の自然な順序: x === 0（0 === x のような yoda 記法を禁止）
      "yoda": "error",
    },
  },
];
