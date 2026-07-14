# -*- coding: utf-8 -*-
Feature: 세탁기 현재 코스 코디네이터 (coordinator_course.py)
  PAT API는 세탁기가 어떤 코스로 돌아가는지 알려주지 않기 때문에,
  이 컴포넌트에서 유일하게 wideq를 폴링하는 지점이다. 불필요한
  wideq 호출을 줄이기 위해 세탁기가 실제로 동작 중일 때만 폴링하고,
  멈추면 즉시 중단하며 표시값을 "-"로 되돌려야 한다.

  Scenario: 세탁기가 동작 중으로 바뀌면 코스 폴링이 시작된다
    Given 세탁기가 꺼진 상태로 코스 코디네이터가 만들어져 있다
    When PAT 세탁기 상태가 RUNNING으로 바뀐다
    Then 코스 폴링은 활성 상태여야 한다

  Scenario: 세탁기가 정지 상태로 바뀌면 코스 폴링이 중단되고 값이 "-"로 초기화된다
    Given 세탁기가 동작 중인 상태로 코스 코디네이터가 만들어져 있다
    When PAT 세탁기 상태가 POWER_OFF로 바뀐다
    Then 코스 폴링은 비활성 상태여야 한다
    And 코스 표시값은 "-" 이어야 한다

  Scenario: 정상적으로 코스 이름을 받으면 그 값을 그대로 사용한다
    Given 세탁기가 동작 중인 상태로 코스 코디네이터가 만들어져 있다
    When wideq가 코스 "표준", 스마트코스 "-"를 반환한다
    Then 코스 결과는 "표준" 이어야 한다

  Scenario: 일반 코스가 없으면 스마트코스 값으로 대체한다
    Given 세탁기가 동작 중인 상태로 코스 코디네이터가 만들어져 있다
    When wideq가 코스 "-", 스마트코스 "이불빨래"를 반환한다
    Then 코스 결과는 "이불빨래" 이어야 한다

  Scenario: 일반 코스와 스마트코스가 모두 없으면 "-"를 반환한다
    Given 세탁기가 동작 중인 상태로 코스 코디네이터가 만들어져 있다
    When wideq가 코스 "-", 스마트코스 "-"를 반환한다
    Then 코스 결과는 "-" 이어야 한다

  Scenario: wideq가 아무 데이터도 못 가져오면 UpdateFailed로 처리된다
    Given 세탁기가 동작 중인 상태로 코스 코디네이터가 만들어져 있다
    When wideq 코스 조회가 데이터 없이(None) 끝난다
    Then 예외는 UpdateFailed 이어야 한다

  Scenario: wideq 코스 조회가 InvalidCredentialError로 실패하면 재인증 필요로 표시된다
    Given 세탁기가 동작 중인 상태로 코스 코디네이터가 만들어져 있다
    When wideq 코스 조회가 InvalidCredentialError로 실패한다
    Then 예외는 UpdateFailed 이어야 한다
    And runtime_data의 재인증 필요 상태는 True 이어야 한다

  Scenario: wideq 코스 조회가 일반 예외로 실패해도 UpdateFailed로 감싸진다
    Given 세탁기가 동작 중인 상태로 코스 코디네이터가 만들어져 있다
    When wideq 코스 조회가 예상치 못한 예외로 실패한다
    Then 예외는 UpdateFailed 이어야 한다

  Scenario: 이미 재인증이 필요한 상태면 wideq 호출 자체를 건너뛴다
    Given 세탁기가 동작 중인 상태로 코스 코디네이터가 만들어져 있다
    When 재인증이 필요한 상태에서 코스 갱신을 시도한다
    Then 예외는 UpdateFailed 이어야 한다
    And wideq poll은 호출되지 않았어야 한다
