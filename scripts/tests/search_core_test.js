"use strict";

const assert = require("node:assert/strict");
const search = require("../../web/assets/search-core.js");

const record = {
  id: "case-2020다247190",
  title: "대법원 2024. 12. 19. 선고 2020다247190 전원합의체 판결",
  summary: "재직조건부 상여금의 통상임금성을 판단하였다.",
};
record.searchNormalised = search.normalise(
  `${record.id} ${record.title} ${record.summary} 판례 변경과 소정근로 대가성`
);

assert.equal(search.normalise("2020 다 247190"), "2020다247190");
assert.equal(search.matchesQuery(record, "2020 다 247190"), true);
assert.equal(search.matchesQuery(record, "통상임금 판례"), true);
assert.equal(search.matchesQuery(record, "최저임금 판례"), false);
assert.ok(search.score(record, search.queryParts("2020다247190")) > 0);

console.log("search-core: all assertions passed");
