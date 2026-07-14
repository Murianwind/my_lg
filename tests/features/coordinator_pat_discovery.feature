# -*- coding: utf-8 -*-
Feature: PAT 기기 발견/생성 및 REST 폴백 (coordinator_pat.py)
  기기 목록을 잘못 걸러내거나, 프로필 로드가 실패했는데 조용히 None을
  반환하는 경우 둘 다 "기기가 그냥 안 보인다"는 조용한 증상으로만
  나타난다. REST 폴백(_async_update_data)은 MQTT push가 안 될 때의
  마지막 안전망이라 이것도 검증해둘 가치가 크다.

  Scenario: 기기 목록이 비어 있으면 빈 목록을 반환한다
    When PAT 기기 목록 조회 결과가 없다
    Then PAT 기기 발견 결과는 빈 목록이어야 한다

  Scenario: 지원하지 않는 기기 타입은 걸러진다
    When PAT 기기 목록에 지원 기기와 미지원 기기가 섞여 있다
    Then PAT 기기 발견 결과에는 지원 기기만 남아야 한다

  Scenario: 지원하지 않는 타입은 기기 객체를 만들지 않는다
    When 지원하지 않는 타입으로 PAT 기기를 생성한다
    Then 생성된 기기는 None 이어야 한다

  Scenario: 프로필 로드가 성공하면 기기 객체가 만들어진다
    When 에어컨 타입으로 PAT 기기를 생성한다
    Then 생성된 기기는 None이 아니어야 한다

  Scenario: 프로필 로드가 실패해도 크래시 없이 None을 반환한다
    When 프로필 로드가 실패하는 상태로 에어컨 타입 PAT 기기를 생성한다
    Then 생성된 기기는 None 이어야 한다

  Scenario: REST 폴백이 정상적으로 상태를 받아오면 available해진다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    When REST 폴백 상태 조회가 성공한다
    Then 코디네이터는 available 이어야 한다

  Scenario: REST 폴백이 빈 상태를 반환하면 UpdateFailed로 처리된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    When REST 폴백이 빈 상태를 반환한다
    Then 예외는 UpdateFailed 이어야 한다

  Scenario: REST 폴백 호출이 실패하면 UpdateFailed로 감싸진다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    When REST 폴백 호출이 실패한다
    Then 예외는 UpdateFailed 이어야 한다
