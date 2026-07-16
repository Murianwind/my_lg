# -*- coding: utf-8 -*-
Feature: PAT 명령의 verify(실제 상태 확인) 경로
  실제 로그에서, PAT가 FAIL_DEVICE_CONTROL로 계속 실패를 응답한 명령이
  약 2.5초 뒤 기기에 실제로 적용된 사례가 확인됐다 - API 응답만으로는
  "정말 실패했는지"를 신뢰할 수 없다는 뜻이다. verify를 넘긴 호출부는
  API가 실패라고 해도, 지연 후 실제 기기 상태를 다시 읽어서 최종
  판단한다.

  Scenario: API는 계속 실패라고 응답해도 기기 상태가 이미 적용됐으면 성공 처리된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    When PAT 명령이 계속 실패로 응답되지만 기기에는 이미 적용되어 있다
    Then 예외가 발생하지 않아야 한다

  Scenario: API도 실패하고 기기 상태도 끝까지 적용 안 되면 최종 실패로 처리된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    When PAT 명령이 계속 실패로 응답되고 기기에도 끝까지 적용되지 않는다
    Then 예외는 ServiceValidationError 이어야 한다

  Scenario: 1차 확인 시점에 이미 적용되어 있으면 재전송 없이 성공 처리된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    When PAT 명령이 실패했지만 1차 확인 시점에 이미 적용되어 있다
    Then 예외가 발생하지 않아야 한다
    And PAT 호출 횟수는 1 이어야 한다

  Scenario: 1차 확인에도 안 되면 명령을 다시 보내서 2차 확인에서 성공한다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    When PAT 명령이 재전송되어야만 실제로 적용된다
    Then 예외가 발생하지 않아야 한다
    And PAT 호출 횟수는 2 이어야 한다
