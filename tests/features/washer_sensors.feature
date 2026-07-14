# -*- coding: utf-8 -*-
Feature: 세탁기 남은시간 센서의 비정상 값 방어
  REMAIN_HOUR/REMAIN_MINUTE는 None이 아니면서도 빈 문자열처럼 숫자로
  변환할 수 없는 값이 올 때가 있다 (기기가 막 꺼졌거나 네트워크가
  불안정할 때). 이런 값이 와도 센서 갱신 전체가 크래시 나면 안 된다.

  Scenario: 정상적인 남은시간 값은 완료 예정 시각으로 변환된다
    Given 남은시간이 1시간 30분인 세탁기 PAT 코디네이터가 있다
    When 세탁기 남은시간 센서의 native_value를 읽는다
    Then native_value는 None이 아니어야 한다

  Scenario: 빈 문자열 남은시간 값은 크래시 없이 None으로 처리된다
    Given 남은시간이 빈 문자열인 세탁기 PAT 코디네이터가 있다
    When 세탁기 남은시간 센서의 native_value를 읽는다
    Then native_value는 None 이어야 한다
    And 예외가 발생하지 않아야 한다

  Scenario: 남은시간이 0분이면 None을 반환한다
    Given 남은시간이 0시간 0분인 세탁기 PAT 코디네이터가 있다
    When 세탁기 남은시간 센서의 native_value를 읽는다
    Then native_value는 None 이어야 한다
