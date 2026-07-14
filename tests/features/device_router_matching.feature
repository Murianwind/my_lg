# -*- coding: utf-8 -*-
Feature: wideq 기기와 PAT 기기 매칭
  두 API는 같은 물리적 기기를 서로 다른 식별자로 노출하므로, 기기
  타입과 사용자가 지정한 별칭(alias)의 조합으로 매칭해야 한다.

  Scenario: 타입과 별칭이 모두 일치하면 매칭된다
    Given PAT 기기 목록에 별칭 "거실에어컨", 타입 DEVICE_AIR_CONDITIONER인 항목이 있다
    When wideq AC 타입, 별칭 "거실에어컨"으로 매칭을 시도한다
    Then 매칭 결과는 None이 아니어야 한다

  Scenario: 별칭이 다르면 매칭되지 않는다
    Given PAT 기기 목록에 별칭 "거실에어컨", 타입 DEVICE_AIR_CONDITIONER인 항목이 있다
    When wideq AC 타입, 별칭 "안방에어컨"으로 매칭을 시도한다
    Then 매칭 결과는 None 이어야 한다

  Scenario: 타입이 호환되지 않으면 매칭되지 않는다
    Given PAT 기기 목록에 별칭 "거실에어컨", 타입 DEVICE_AIR_CONDITIONER인 항목이 있다
    When wideq WASHER 타입, 별칭 "거실에어컨"으로 매칭을 시도한다
    Then 매칭 결과는 None 이어야 한다
