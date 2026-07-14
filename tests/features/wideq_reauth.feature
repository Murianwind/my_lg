# -*- coding: utf-8 -*-
Feature: wideq 재인증 필요 상태 관리
  LG 서버는 진짜 자격 증명 오류와 "새 약관 동의 필요"를 같은
  InvalidCredentialError(0110)로 반환하기 때문에 구분할 수 없다.
  이 상태가 감지되면 이후 wideq 호출은 전부 건너뛰어야 하고,
  binary_sensor로 사용자에게 알릴 수 있어야 한다.

  Scenario: InvalidCredentialError를 받으면 재인증 필요 상태가 된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 팬/스윙 연동 기기(풍속 2단계, 수직 스텝 2단계)가 있다
    And 이 코디네이터와 wideq 기기로 climate 엔티티를 만든다
    When wideq 명령이 InvalidCredentialError로 실패한다
    Then runtime_data의 재인증 필요 상태는 True 이어야 한다

  Scenario: 재인증이 필요한 동안에는 이후 wideq 명령이 조용히 건너뛰어진다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 팬/스윙 연동 기기(풍속 2단계, 수직 스텝 2단계)가 있다
    And 이 코디네이터와 wideq 기기로 climate 엔티티를 만든다
    And wideq 명령이 InvalidCredentialError로 실패한다
    When 재인증이 필요한 상태에서 wideq 명령을 다시 시도한다
    Then 예외가 발생하지 않아야 한다

  Scenario: AC 필터 정보 조회가 InvalidCredentialError로 실패해도 크래시 없이 재인증 필요로 처리된다
    Given 빈 runtime_data가 있다
    When AC 필터 조회가 InvalidCredentialError로 실패한다
    Then 예외는 UpdateFailed 이어야 한다
    And runtime_data의 재인증 필요 상태는 True 이어야 한다
